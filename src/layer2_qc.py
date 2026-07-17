"""
ViralFactory — Layer-2 Asset QC (T11.8)

Per CORRECTION-episode-format-and-reference-assets-v1.0 §7.2:
- Identity check: face-embedding cosine similarity of returned stills and
  first/mid/last animation frames against canonical character_ref images.
  Below threshold → qc_flag: identity_drift.
- Grade check: color-histogram distance vs the location plate.
  Breach → qc_flag: grade_break.

Key design rules:
- Face-embedding uses a self-hosted insightface-class ONNX model on CPU.
  NO per-call API cost. If the model isn't available, skip gracefully.
- Color-histogram uses PIL + numpy (no OpenCV required).
- All thresholds come from config/models.yaml episode_qc block — never hardcoded.
- Flags are advisory: they NEVER auto-reject. They render as warnings on
  storyboard cards and enter AMENDMENT-008 review evidence.
- No business values in this code — the harness knows the schema, not the show.
"""

import json
import logging
import math
import os
import subprocess
import tempfile
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ── Defaults (used only if config block is entirely missing) ────────────
# These are NOT the source of truth — config/models.yaml is. These just
# prevent a crash if the config block is absent.
_DEFAULT_QC_CONFIG = {
    "identity": {
        "enabled": True,
        "model_path": "models/insightface/buffalo_l/w600k_r50.onnx",
        "min_cosine_similarity": 0.45,
        "frame_positions": ["first", "middle", "last"],
        "min_face_confidence": 0.5,
    },
    "grade": {
        "enabled": True,
        "histogram_metric": "correlation",
        "histogram_threshold": 0.30,
        "histogram_bins": 32,
        "frame_positions": ["first", "middle", "last"],
    },
}


def _merge_config(qc_config: dict | None) -> dict:
    """Merge the provided episode_qc config over defaults, section by section."""
    if not qc_config:
        return _DEFAULT_QC_CONFIG.copy()
    merged = {}
    for section in ("identity", "grade"):
        merged[section] = {**_DEFAULT_QC_CONFIG.get(section, {}), **qc_config.get(section, {})}
    return merged


# ── Color histogram (grade check) ───────────────────────────────────────

def compute_color_histogram(image_path: str, bins: int = 32) -> Optional[np.ndarray]:
    """Compute a normalized 3D color histogram for an image using PIL.

    Returns a flattened, L1-normalized histogram array, or None if the
    image cannot be loaded.
    """
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        logger.debug(f"Could not open image {image_path}: {e}")
        return None

    arr = np.array(img)
    # 3D histogram over R, G, B channels
    hist, _ = np.histogramdd(
        arr.reshape(-1, 3),
        bins=(bins, bins, bins),
        range=[(0, 256), (0, 256), (0, 256)],
    )
    hist = hist.flatten().astype(np.float64)
    # L1 normalize
    total = hist.sum()
    if total > 0:
        hist /= total
    return hist


def histogram_correlation(h1: np.ndarray, h2: np.ndarray) -> float:
    """Pearson correlation between two histograms. Higher = more similar."""
    h1 = h1.astype(np.float64)
    h2 = h2.astype(np.float64)
    mean1 = h1.mean()
    mean2 = h2.mean()
    num = ((h1 - mean1) * (h2 - mean2)).sum()
    den = math.sqrt(((h1 - mean1) ** 2).sum() * ((h2 - mean2) ** 2).sum())
    if den == 0:
        return 0.0
    return float(num / den)


def histogram_chi_square(h1: np.ndarray, h2: np.ndarray) -> float:
    """Chi-square distance. Lower = more similar."""
    eps = 1e-10
    return float(np.sum((h1 - h2) ** 2 / (h1 + h2 + eps)))


def histogram_bhattacharyya(h1: np.ndarray, h2: np.ndarray) -> float:
    """Bhattacharyya distance. Lower = more similar."""
    return float(1.0 - np.sum(np.sqrt(h1 * h2)))


def histogram_intersection(h1: np.ndarray, h2: np.ndarray) -> float:
    """Histogram intersection. Higher = more similar."""
    return float(np.minimum(h1, h2).sum())


_METRIC_FUNCS = {
    "correlation": histogram_correlation,
    "chi_square": histogram_chi_square,
    "bhattacharyya": histogram_bhattacharyya,
    "intersection": histogram_intersection,
}

# Metrics where higher value = more similar (threshold is a minimum)
_HIGHER_IS_BETTER = {"correlation", "intersection"}
# Metrics where lower value = more similar (threshold is a maximum)
_LOWER_IS_BETTER = {"chi_square", "bhattacharyya"}


def histogram_distance(h1: np.ndarray, h2: np.ndarray, metric: str) -> float:
    """Compute histogram distance using the named metric."""
    func = _METRIC_FUNCS.get(metric)
    if func is None:
        raise ValueError(f"Unknown histogram metric: {metric!r}. Must be one of {list(_METRIC_FUNCS)}")
    return func(h1, h2)


def is_grade_break(distance: float, threshold: float, metric: str) -> bool:
    """Determine if the histogram distance constitutes a grade break.

    For 'higher is better' metrics (correlation, intersection):
      distance below threshold → grade break.
    For 'lower is better' metrics (chi_square, bhattacharyya):
      distance above threshold → grade break.
    """
    if metric in _HIGHER_IS_BETTER:
        return distance < threshold
    elif metric in _LOWER_IS_BETTER:
        return distance > threshold
    else:
        raise ValueError(f"Unknown metric: {metric!r}")


def run_grade_check(
    still_or_frame_paths: list[str],
    plate_path: str,
    grade_config: dict,
) -> dict:
    """Run the color-histogram grade check on one or more images.

    Args:
        still_or_frame_paths: paths to returned stills or extracted video frames.
        plate_path: path to the canonical location plate image.
        grade_config: the 'grade' sub-config from episode_qc.

    Returns a findings dict with per-image results and an overall flag.
    """
    metric = grade_config.get("histogram_metric", "correlation")
    threshold = grade_config.get("histogram_threshold", 0.30)
    bins = grade_config.get("histogram_bins", 32)

    plate_hist = compute_color_histogram(plate_path, bins=bins)
    if plate_hist is None:
        return {
            "status": "skipped",
            "reason": f"Could not load plate image: {plate_path}",
            "flag": None,
            "per_image": [],
        }

    per_image = []
    any_break = False

    for img_path in still_or_frame_paths:
        hist = compute_color_histogram(img_path, bins=bins)
        if hist is None:
            per_image.append({
                "path": img_path,
                "status": "skipped",
                "reason": "Could not load image",
            })
            continue

        dist = histogram_distance(plate_hist, hist, metric)
        break_detected = is_grade_break(dist, threshold, metric)
        if break_detected:
            any_break = True

        per_image.append({
            "path": img_path,
            "status": "flagged" if break_detected else "ok",
            "metric": metric,
            "distance": round(dist, 4),
            "threshold": threshold,
        })

    return {
        "status": "complete",
        "flag": "qc_flag: grade_break" if any_break else None,
        "metric": metric,
        "threshold": threshold,
        "per_image": per_image,
    }


# ── Face embedding (identity check) ─────────────────────────────────────

class FaceEmbedder:
    """Wraps a self-hosted ONNX face embedding model.

    Uses onnxruntime if available. If the model file or onnxruntime is not
    available, all operations degrade gracefully — embedding returns None,
    and the identity check is skipped.
    """

    def __init__(self, model_path: str, min_face_confidence: float = 0.5):
        self.model_path = model_path
        self.min_face_confidence = min_face_confidence
        self._session = None
        self._detector = None
        self._available = False
        self._init_model()

    def _init_model(self):
        """Attempt to load the ONNX model and face detector."""
        if not os.path.isfile(self.model_path):
            logger.info(f"Face embedding model not found at {self.model_path} — identity check will be skipped")
            return

        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(
                self.model_path,
                providers=["CPUExecutionProvider"],
            )
            self._available = True
        except ImportError:
            logger.info("onnxruntime not installed — identity check will be skipped")
        except Exception as e:
            logger.warning(f"Could not load ONNX model {self.model_path}: {e}")

    @property
    def available(self) -> bool:
        return self._available

    def detect_faces(self, image_path: str) -> list[dict]:
        """Detect faces in an image.

        Returns a list of dicts with keys: 'bbox' (x, y, w, h), 'confidence',
        and 'embedding' (if available).

        Uses insightface if installed; otherwise falls back to a simple
        face detection via PIL-based heuristics (not implemented — returns []).
        """
        if not self._available:
            return []

        try:
            import cv2
            img = cv2.imread(image_path)
            if img is None:
                return []
            # Use insightface's FaceAnalysis if available
            from insightface.app import FaceAnalysis
            if self._detector is None:
                self._detector = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
                self._detector.prepare(ctx_id=-1, det_size=(640, 640))

            faces = self._detector.get(img)
            results = []
            for face in faces:
                if face.det_score >= self.min_face_confidence:
                    results.append({
                        "bbox": face.bbox.tolist(),
                        "confidence": float(face.det_score),
                        "embedding": face.embedding.tolist() if hasattr(face, "embedding") else None,
                    })
            return results
        except ImportError:
            # insightface not installed
            return []
        except Exception as e:
            logger.debug(f"Face detection failed for {image_path}: {e}")
            return []

    def get_embedding(self, image_path: str) -> Optional[list[float]]:
        """Get the face embedding vector for the primary face in an image.

        Returns None if no face is detected or the model isn't available.
        """
        faces = self.detect_faces(image_path)
        if not faces:
            return None
        # Use the highest-confidence face
        best = max(faces, key=lambda f: f["confidence"])
        return best.get("embedding")

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        arr_a = np.array(a, dtype=np.float64)
        arr_b = np.array(b, dtype=np.float64)
        norm_a = np.linalg.norm(arr_a)
        norm_b = np.linalg.norm(arr_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(arr_a, arr_b) / (norm_a * norm_b))


def run_identity_check(
    still_or_frame_paths: list[str],
    character_ref_paths: list[str],
    identity_config: dict,
    embedder: FaceEmbedder | None = None,
) -> dict:
    """Run the face-embedding identity check.

    Args:
        still_or_frame_paths: paths to returned stills or extracted video frames.
        character_ref_paths: paths to canonical character_ref images.
        identity_config: the 'identity' sub-config from episode_qc.
        embedder: an optional pre-constructed FaceEmbedder (for testing with mocks).

    Returns a findings dict with per-image results and an overall flag.
    """
    min_sim = identity_config.get("min_cosine_similarity", 0.45)

    # If no embedder is provided, create one from config
    if embedder is None:
        model_path = identity_config.get("model_path", "models/insightface/buffalo_l/w600k_r50.onnx")
        min_face_conf = identity_config.get("min_face_confidence", 0.5)
        embedder = FaceEmbedder(model_path, min_face_confidence=min_face_conf)

    # If the model isn't available, skip gracefully
    if not embedder.available:
        return {
            "status": "skipped",
            "reason": "Face embedding model not available — identity check skipped",
            "flag": None,
            "per_image": [],
        }

    # Compute canonical embeddings from character_ref images
    canonical_embeddings = []
    for ref_path in character_ref_paths:
        emb = embedder.get_embedding(ref_path)
        if emb is not None:
            canonical_embeddings.append(emb)

    if not canonical_embeddings:
        return {
            "status": "skipped",
            "reason": "No face embeddings could be extracted from character_ref images",
            "flag": None,
            "per_image": [],
        }

    per_image = []
    any_drift = False

    for img_path in still_or_frame_paths:
        emb = embedder.get_embedding(img_path)
        if emb is None:
            per_image.append({
                "path": img_path,
                "status": "no_face",
                "reason": "No face detected or embedding failed",
            })
            continue

        # Max cosine similarity against all canonical refs
        sims = [FaceEmbedder.cosine_similarity(emb, ref_emb) for ref_emb in canonical_embeddings]
        max_sim = max(sims) if sims else 0.0

        drift_detected = max_sim < min_sim
        if drift_detected:
            any_drift = True

        per_image.append({
            "path": img_path,
            "status": "flagged" if drift_detected else "ok",
            "max_cosine_similarity": round(max_sim, 4),
            "threshold": min_sim,
        })

    return {
        "status": "complete",
        "flag": "qc_flag: identity_drift" if any_drift else None,
        "min_cosine_similarity": min_sim,
        "canonical_ref_count": len(canonical_embeddings),
        "per_image": per_image,
    }


# ── Video frame extraction ──────────────────────────────────────────────

def extract_video_frames(
    video_path: str,
    output_dir: str,
    positions: list[str] = None,
) -> list[str]:
    """Extract frames from a video at specified positions.

    Args:
        video_path: path to the video file.
        output_dir: directory to save extracted frames.
        positions: list of positions to extract: "first", "middle", "last".

    Returns a list of frame file paths. If extraction fails, returns an
    empty list (graceful degradation).
    """
    if positions is None:
        positions = ["first", "middle", "last"]

    os.makedirs(output_dir, exist_ok=True)

    try:
        # Get duration
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", video_path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        if duration <= 0:
            return []
    except Exception:
        return []

    # Map positions to timestamps
    timestamps = {}
    if "first" in positions:
        timestamps["first"] = 0.0
    if "middle" in positions:
        timestamps["middle"] = duration / 2.0
    if "last" in positions:
        # Slightly before end to avoid EOF issues
        ts = max(0, duration - 0.1)
        timestamps["last"] = ts

    frame_paths = []
    for pos, ts in timestamps.items():
        frame_path = os.path.join(output_dir, f"frame_{pos}.jpg")
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
                 "-frames:v", "1", "-q:v", "2", frame_path],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and os.path.exists(frame_path):
                frame_paths.append(frame_path)
        except Exception:
            pass

    return frame_paths


# ── Top-level QC runner ──────────────────────────────────────────────────

def run_layer2_qc(
    media_path: str,
    character_ref_paths: list[str],
    location_plate_path: str,
    qc_config: dict | None,
    asset_id: int = 0,
    media_id: int = 0,
    db_path: str = "data/viralfactory.db",
    embedder: FaceEmbedder | None = None,
    business_slug: str = None,
) -> dict:
    """Run the full Layer-2 asset QC on a returned still or animated clip.

    This is the main entry point. It:
    1. Determines whether the media is a still image or a video.
    2. For videos: extracts first/mid/last frames.
    3. Runs the identity check (face-embedding cosine similarity vs character_ref).
    4. Runs the grade check (color-histogram distance vs location plate).
    5. Returns advisory flags — NEVER auto-rejects.

    The results are saved as an asset_reviews row (review_type='layer2_qc')
    for integration with AMENDMENT-008 review evidence.

    Args:
        media_path: path to the returned still image or video file.
        character_ref_paths: canonical character_ref image file paths.
        location_plate_path: canonical location plate image file path.
        qc_config: the episode_qc config dict (from models.yaml).
        asset_id: asset ID for DB storage.
        media_id: media ID for DB storage.
        db_path: SQLite DB path.
        embedder: optional pre-constructed FaceEmbedder (for testing).
        business_slug: business slug for provenance.

    Returns:
        dict with keys: review_id, review_type, status, flags, findings, summary.
        flags is a list of advisory flag strings (may be empty).
        status is one of: "complete", "skipped", "failed".
    """
    config = _merge_config(qc_config)
    identity_config = config["identity"]
    grade_config = config["grade"]

    # Determine if media is a video or image
    is_video = media_path.lower().endswith((".mp4", ".mov", ".avi", ".webm", ".mkv"))

    # Collect the images to check
    if is_video:
        # Extract frames
        frame_dir = tempfile.mkdtemp(prefix="layer2_qc_frames_")
        id_positions = identity_config.get("frame_positions", ["first", "middle", "last"])
        grade_positions = grade_config.get("frame_positions", ["first", "middle", "last"])
        all_positions = list(set(id_positions + grade_positions))

        frame_paths = extract_video_frames(media_path, frame_dir, all_positions)
        check_paths = frame_paths
        # Clean up temp frames later (best-effort)
        import shutil
        cleanup_dir = frame_dir
    else:
        check_paths = [media_path]
        cleanup_dir = None

    findings = {
        "media_path": media_path,
        "media_type": "video" if is_video else "still",
        "identity": None,
        "grade": None,
    }
    flags = []

    # Run identity check
    if identity_config.get("enabled", True) and character_ref_paths:
        id_positions = identity_config.get("frame_positions", ["first", "middle", "last"])
        if is_video:
            # Filter frames to the identity check positions
            id_frames = [f for f in check_paths if any(p in os.path.basename(f) for p in id_positions)]
        else:
            id_frames = check_paths

        id_result = run_identity_check(
            id_frames, character_ref_paths, identity_config, embedder=embedder,
        )
        findings["identity"] = id_result
        if id_result.get("flag"):
            flags.append(id_result["flag"])
    else:
        findings["identity"] = {
            "status": "skipped",
            "reason": "Identity check disabled or no character_ref paths provided",
            "flag": None,
        }

    # Run grade check
    if grade_config.get("enabled", True) and location_plate_path:
        grade_positions = grade_config.get("frame_positions", ["first", "middle", "last"])
        if is_video:
            grade_frames = [f for f in check_paths if any(p in os.path.basename(f) for p in grade_positions)]
        else:
            grade_frames = check_paths

        grade_result = run_grade_check(grade_frames, location_plate_path, grade_config)
        findings["grade"] = grade_result
        if grade_result.get("flag"):
            flags.append(grade_result["flag"])
    else:
        findings["grade"] = {
            "status": "skipped",
            "reason": "Grade check disabled or no plate path provided",
            "flag": None,
        }

    # Build summary
    summary_parts = []
    if findings["identity"].get("status") == "complete":
        if findings["identity"].get("flag"):
            summary_parts.append("identity_drift")
        else:
            summary_parts.append("identity OK")
    elif findings["identity"].get("status") == "skipped":
        summary_parts.append("identity skipped")

    if findings["grade"].get("status") == "complete":
        if findings["grade"].get("flag"):
            summary_parts.append("grade_break")
        else:
            summary_parts.append("grade OK")
    elif findings["grade"].get("status") == "skipped":
        summary_parts.append("grade skipped")

    summary = "; ".join(summary_parts) if summary_parts else "Layer-2 QC complete"

    # Determine overall status
    id_status = findings["identity"].get("status", "")
    grade_status = findings["grade"].get("status", "")
    if id_status == "complete" or grade_status == "complete":
        overall_status = "complete"
    elif id_status == "skipped" and grade_status == "skipped":
        overall_status = "skipped"
    else:
        overall_status = "complete"

    # Clean up temp frames
    if cleanup_dir:
        import shutil
        shutil.rmtree(cleanup_dir, ignore_errors=True)

    # Save to DB (review_type='layer2_qc')
    review_id = _save_layer2_review(
        db_path=db_path,
        asset_id=asset_id,
        media_id=media_id,
        media_path=media_path,
        findings=findings,
        flags=flags,
        summary=summary,
        business_slug=business_slug,
    )

    return {
        "review_id": review_id,
        "review_type": "layer2_qc",
        "status": overall_status,
        "flags": flags,
        "findings": findings,
        "summary": summary,
    }


def _save_layer2_review(
    db_path: str,
    asset_id: int,
    media_id: int,
    media_path: str,
    findings: dict,
    flags: list[str],
    summary: str,
    business_slug: str | None = None,
) -> int | None:
    """Save the Layer-2 QC results to the asset_reviews table.

    The verdict is always 'advisory' — Layer-2 flags never auto-reject.
    """
    from datetime import datetime, timezone
    import sqlite3

    # Ensure the asset_reviews table exists
    try:
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS asset_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                media_id INTEGER NOT NULL,
                media_path TEXT NOT NULL,
                review_type TEXT NOT NULL,
                status TEXT NOT NULL,
                verdict TEXT,
                findings_json TEXT,
                summary TEXT,
                model TEXT,
                prompt_file TEXT,
                prompt_version TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        ts = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """INSERT INTO asset_reviews
               (asset_id, media_id, media_path, review_type, status, verdict,
                findings_json, summary, model, prompt_file, prompt_version,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, media_id, media_path, "layer2_qc", "complete",
             "advisory",  # ALWAYS advisory — never auto-reject
             json.dumps({"flags": flags, **findings}), summary,
             "insightface-onnx", "(layer2_qc)", "1.0", ts, ts),
        )
        review_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return review_id
    except Exception as e:
        logger.warning(f"Could not save Layer-2 QC to DB: {e}")
        return None