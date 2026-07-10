"""
ViralFactory — Asset Review Layer

Per CORRECTION-final-output-review-and-audio-fix-v1.0 Part 2:
- Mechanical post-render checks (ASSET-REVIEW-1): deterministic ffprobe checks
  after every render — file size, duration, stream presence, resolution, SAR.
- Vision-based visual inspection (ASSET-REVIEW-2): keyframe extraction + vision
  LLM examines frames vs content.
- Audio inspection (ASSET-REVIEW-3): whisper transcription + loop detection.
- Content alignment (ASSET-REVIEW-4): aggregates all checks into a single verdict.
- Image review (ASSET-REVIEW-6): lightweight vision check on standalone images.

The review is advisory, not blocking. The operator is always the final gate.
Every LLM call goes through the adapter with full provenance.
"""

import json
import os
import subprocess
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

# Support both package and direct imports
try:
    from .provenance import ProvenanceLog
except ImportError:
    from provenance import ProvenanceLog


ASSET_REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    media_id INTEGER NOT NULL,          -- asset_media row this review is about
    media_path TEXT NOT NULL,
    review_type TEXT NOT NULL,           -- mechanical | visual | audio | alignment | image
    status TEXT NOT NULL,                -- pending | running | complete | failed
    verdict TEXT,                        -- pass | issues_found | ready_for_operator | needs_rerender
    findings_json TEXT,                  -- full JSON findings
    summary TEXT,                        -- plain-language summary for operator
    model TEXT,                          -- model used (for LLM-based reviews)
    prompt_file TEXT,                    -- prompt file used (for LLM-based reviews)
    prompt_version TEXT,                 -- prompt version
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    FOREIGN KEY (media_id) REFERENCES asset_media(id)
);

CREATE INDEX IF NOT EXISTS idx_asset_reviews_asset ON asset_reviews(asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_reviews_media ON asset_reviews(media_id);
CREATE INDEX IF NOT EXISTS idx_asset_reviews_type ON asset_reviews(review_type);
"""


class AssetReviewer:
    """
    Runs mechanical + AI checks on rendered output.

    Usage:
        reviewer = AssetReviewer(models_config, db_path="data/viralfactory.db")
        review = reviewer.review_render(output_path, plan, asset_id, media_id)
        # review = {"verdict": "pass", "summary": "...", "findings": {...}}
    """

    def __init__(self, models_config: dict, db_path: str = "data/viralfactory.db"):
        self.models_config = models_config
        self.db_path = db_path
        self.provenance = ProvenanceLog(db_path)
        self._init_tables()

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(ASSET_REVIEW_SCHEMA)
        conn.commit()
        conn.close()

    # ── ffprobe helpers (shared with assembly.py but standalone) ─────────

    def _probe(self, file_path: str) -> dict:
        """Run ffprobe and return full stream/format info."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", file_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return {}
            return json.loads(result.stdout)
        except Exception:
            return {}

    def _get_duration(self, file_path: str) -> float:
        data = self._probe(file_path)
        return float(data.get("format", {}).get("duration", 0))

    def _has_stream(self, file_path: str, codec_type: str) -> bool:
        data = self._probe(file_path)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == codec_type:
                return True
        return False

    def _get_resolution(self, file_path: str) -> tuple:
        data = self._probe(file_path)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return (int(stream.get("width", 0)), int(stream.get("height", 0)))
        return (0, 0)

    def _get_sar(self, file_path: str) -> str:
        data = self._probe(file_path)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return stream.get("sample_aspect_ratio", "1:1")
        return "1:1"

    def _is_silent_audio(self, file_path: str) -> bool:
        """Check if the audio track is silent (all zeros or -inf mean volume)."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-i", file_path, "-vn", "-ac", "1",
                 "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, timeout=60,
            )
            for line in result.stderr.split("\n"):
                if "mean_volume" in line:
                    vol_str = line.split("mean_volume:")[1].strip()
                    if vol_str == "-inf":
                        return True
                    vol_db = float(vol_str.replace(" dB", ""))
                    return vol_db < -50
            return True  # No audio at all = silent
        except Exception:
            return True

    # ── ASSET-REVIEW-1: Mechanical post-render checks ────────────────────

    def run_mechanical_checks(self, file_path: str, plan: dict) -> dict:
        """Run deterministic ffprobe-based checks on the rendered output.

        No LLM calls — pure mechanical. Returns a findings dict.
        """
        checks = {
            "file_exists": os.path.exists(file_path),
            "file_size_kb": 0,
            "duration_s": 0,
            "has_video_stream": False,
            "has_audio_stream": False,
            "resolution": [0, 0],
            "sar": "1:1",
            "warnings": [],
        }

        if not checks["file_exists"]:
            checks["warnings"].append("Output file does not exist")
            return checks

        checks["file_size_kb"] = round(os.path.getsize(file_path) / 1024, 1)

        if checks["file_size_kb"] < 1:
            checks["warnings"].append("Output file is less than 1KB — likely corrupt")

        checks["duration_s"] = round(self._get_duration(file_path), 1)
        checks["has_video_stream"] = self._has_stream(file_path, "video")
        checks["has_audio_stream"] = self._has_stream(file_path, "audio")
        checks["resolution"] = list(self._get_resolution(file_path))
        checks["sar"] = self._get_sar(file_path)

        # Compare to plan
        canvas = plan.get("canvas", {})
        plan_duration = canvas.get("duration_target", 0)
        plan_resolution = canvas.get("resolution", "")

        if plan_duration and checks["duration_s"] > 0:
            duration_diff = abs(checks["duration_s"] - plan_duration)
            if duration_diff > 2.0:
                checks["warnings"].append(
                    f"Duration mismatch: output is {checks['duration_s']}s, "
                    f"plan target is {plan_duration}s (diff: {duration_diff:.1f}s)"
                )

        if plan_resolution and checks["resolution"] != [0, 0]:
            plan_w, plan_h = plan_resolution.split("x")
            plan_res = [int(plan_w), int(plan_h)]
            if checks["resolution"] != plan_res:
                checks["warnings"].append(
                    f"Resolution mismatch: output is {checks['resolution'][0]}x{checks['resolution'][1]}, "
                    f"plan target is {plan_res[0]}x{plan_res[1]}"
                )

        # Audio expectations vs reality
        audio_block = plan.get("audio", {})
        original_audio = audio_block.get("original_audio", False)
        music = audio_block.get("music", {})
        music_ref = music.get("stock_ref") if music else None
        expects_sound = original_audio or bool(music_ref)

        if expects_sound and checks["has_audio_stream"]:
            if self._is_silent_audio(file_path):
                checks["warnings"].append(
                    "Audio expected (original_audio or music) but output audio is silent"
                )
        elif not expects_sound and checks["has_audio_stream"]:
            if not self._is_silent_audio(file_path):
                checks["warnings"].append(
                    "Plan says no audio (original_audio=false, no music) but output has non-silent audio"
                )
        elif expects_sound and not checks["has_audio_stream"]:
            checks["warnings"].append(
                "Audio expected but output has no audio stream"
            )

        return checks

    def _save_review(self, asset_id: int, media_id: int, media_path: str,
                     review_type: str, status: str, verdict: str,
                     findings: dict, summary: str,
                     model: str = None, prompt_file: str = None,
                     prompt_version: str = None) -> int:
        """Save a review result to the asset_reviews table."""
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """INSERT INTO asset_reviews
               (asset_id, media_id, media_path, review_type, status, verdict,
                findings_json, summary, model, prompt_file, prompt_version,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, media_id, media_path, review_type, status, verdict,
             json.dumps(findings), summary, model, prompt_file, prompt_version,
             ts, ts),
        )
        review_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return review_id

    def _log_provenance(self, asset_id: int, review_type: str,
                        message: str, verdict: str,
                        model: str = "mechanical", provider: str = "local",
                        prompt_file: str = "(asset_review)", prompt_version: str = "1.0",
                        business_slug: str = None):
        """Log review to provenance."""
        import hashlib
        self.provenance.log(
            input_hash=hashlib.sha256(f"review:{review_type}:{asset_id}".encode()).hexdigest(),
            prompt_file=prompt_file,
            prompt_version=prompt_version,
            model=model,
            provider=provider,
            raw_output=message,
            validated_output={"asset_id": asset_id, "review_type": review_type, "message": message},
            validator_verdict=verdict,
            context=f"Asset review ({review_type}) for asset {asset_id}",
            temperature=0,
            business_slug=business_slug,
        )

    def review_render(self, output_path: str, plan: dict, asset_id: int,
                      media_id: int, business_slug: str = None) -> dict:
        """Run mechanical checks on a rendered video.

        This is the entry point called after render completes.
        Returns the mechanical check findings + saved review record.
        """
        findings = self.run_mechanical_checks(output_path, plan)

        verdict = "pass" if not findings["warnings"] else "issues_found"
        summary = self._mechanical_summary(findings)

        review_id = self._save_review(
            asset_id=asset_id,
            media_id=media_id,
            media_path=output_path,
            review_type="mechanical",
            status="complete",
            verdict=verdict,
            findings=findings,
            summary=summary,
        )

        self._log_provenance(
            asset_id, "mechanical",
            f"Mechanical checks: {verdict}. {summary}",
            verdict, business_slug=business_slug,
        )

        return {
            "review_id": review_id,
            "review_type": "mechanical",
            "verdict": verdict,
            "findings": findings,
            "summary": summary,
        }

    def _mechanical_summary(self, findings: dict) -> str:
        """Generate a plain-language summary of mechanical check results."""
        parts = []
        parts.append(f"File: {findings['file_size_kb']}KB")
        if findings["duration_s"]:
            parts.append(f"Duration: {findings['duration_s']}s")
        if findings["resolution"] != [0, 0]:
            parts.append(f"Resolution: {findings['resolution'][0]}×{findings['resolution'][1]}")
        parts.append(f"Video stream: {'yes' if findings['has_video_stream'] else 'no'}")
        parts.append(f"Audio stream: {'yes' if findings['has_audio_stream'] else 'no'}")

        if findings["warnings"]:
            parts.append(f"Warnings: {'; '.join(findings['warnings'])}")
        else:
            parts.append("All mechanical checks passed")

        return ". ".join(parts)

    # ── Query helpers for UI ──────────────────────────────────────────────

    def get_reviews_for_media(self, media_id: int) -> list:
        """Get all reviews for a specific media item."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM asset_reviews WHERE media_id = ? ORDER BY created_at DESC",
            (media_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_reviews_for_asset(self, asset_id: int) -> list:
        """Get all reviews for an asset (across all media items)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM asset_reviews WHERE asset_id = ? ORDER BY created_at DESC",
            (asset_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_latest_review_summary(self, media_id: int) -> Optional[dict]:
        """Get the latest review summary for a media item (for UI display)."""
        reviews = self.get_reviews_for_media(media_id)
        if not reviews:
            return None
        # Prefer alignment > mechanical > visual > audio
        type_priority = {"alignment": 0, "mechanical": 1, "visual": 2, "audio": 3, "image": 4}
        reviews.sort(key=lambda r: type_priority.get(r.get("review_type", ""), 99))
        latest = reviews[0]
        return {
            "review_id": latest["id"],
            "review_type": latest["review_type"],
            "status": latest["status"],
            "verdict": latest["verdict"],
            "summary": latest["summary"],
            "findings": json.loads(latest.get("findings_json") or "{}"),
            "created_at": latest["created_at"],
        }

    # ── ASSET-REVIEW-2: Vision-based visual inspection ───────────────────

    def _extract_keyframes(self, video_path: str, output_dir: str,
                           max_frames: int = 5) -> list:
        """Extract keyframes from a video at 20%, 40%, 60%, 80% of duration + first frame.

        Returns list of (frame_index, file_path) tuples.
        """
        duration = self._get_duration(video_path)
        if duration <= 0:
            return []

        # Extract at: 0, 20%, 40%, 60%, 80%
        timestamps = [0]
        if max_frames > 1:
            for i in range(1, max_frames):
                t = duration * (i / max_frames)
                timestamps.append(round(t, 1))

        keyframes = []
        for i, t in enumerate(timestamps):
            frame_path = os.path.join(output_dir, f"keyframe_{i}.jpg")
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(t),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                frame_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and os.path.exists(frame_path):
                keyframes.append((i, frame_path))
        return keyframes

    def _encode_image_b64(self, file_path: str) -> str:
        """Encode an image file as base64 data URL."""
        import base64
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
        return f"data:image/{mime};base64,{data}"

    def _load_prompt_template(self, prompt_file: str) -> tuple:
        """Load a prompt template and extract its version.

        Returns (template_text, version_string).
        """
        import re
        prompt_path = os.path.join("prompts", prompt_file)
        with open(prompt_path) as f:
            content = f.read()
        m = re.search(r'<!-- version: ([\d.]+) -->', content)
        version = m.group(1) if m else "1.0"
        return content, version

    def _render_prompt(self, template: str, variables: dict) -> str:
        """Render a prompt template with variables."""
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace("{" + key + "}", str(value))
        return rendered

    def _call_vision_model(self, model: str, base_url: str, api_key: str,
                           text_prompt: str, image_data_urls: list) -> dict:
        """Call a vision-capable LLM via OpenRouter-compatible API.

        Returns parsed JSON response from the model.
        """
        import requests

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text_prompt},
                ],
            }
        ]

        # Add images to the message content
        for img_url in image_data_urls:
            messages[0]["content"].append({
                "type": "image_url",
                "image_url": {"url": img_url},
            })

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }

        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code != 200:
            raise Exception(f"Vision API error {response.status_code}: {response.text[:500]}")

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return json.loads(content)

    def run_visual_inspection(self, video_path: str, plan: dict,
                              asset_content: str, asset_id: int,
                              media_id: int, business_slug: str = None) -> dict:
        """ASSET-REVIEW-2: Vision-based visual inspection.

        Extracts keyframes, sends them + content to a vision LLM, gets back
        a structured review of whether the visuals match the content.
        """
        review_config = self.models_config.get("asset_review", {})
        enabled = review_config.get("enabled", True)

        if not enabled:
            return {
                "review_type": "visual",
                "status": "skipped",
                "verdict": "skipped",
                "summary": "AI visual review is disabled in config",
                "findings": {},
            }

        # Check if vision model is configured
        vision_model = review_config.get("vision_model")
        api_key_env = review_config.get("vision_api_key_env", "OPENROUTER_API_KEY")
        api_key = os.environ.get(api_key_env, "")

        if not vision_model or not api_key:
            return {
                "review_type": "visual",
                "status": "skipped",
                "verdict": "skipped",
                "summary": "Vision model not configured or API key not set — visual inspection skipped",
                "findings": {},
            }

        # Extract keyframes
        max_keyframes = review_config.get("max_keyframes", 5)
        keyframe_dir = os.path.join(os.path.dirname(video_path), f"review_keyframes_{media_id}")
        os.makedirs(keyframe_dir, exist_ok=True)

        keyframes = self._extract_keyframes(video_path, keyframe_dir, max_keyframes)

        if not keyframes:
            return {
                "review_type": "visual",
                "status": "failed",
                "verdict": "issues_found",
                "summary": "Could not extract keyframes from the video",
                "findings": {"error": "keyframe extraction failed"},
            }

        # Build segment descriptions for the prompt
        segments = plan.get("segments", [])
        seg_descs = []
        for i, seg in enumerate(segments):
            overlays = seg.get("overlays", [])
            caption = ""
            for ov in overlays:
                if ov.get("type") == "caption" and ov.get("text"):
                    caption = ov["text"][:80]
                    break
            seg_descs.append(f"Segment {i+1}: source={seg.get('source','?')}, "
                             f"in={seg.get('in',0)}s, out={seg.get('out',0)}s"
                             f"{', caption: ' + caption if caption else ''}")

        # Load and render the prompt
        template, prompt_version = self._load_prompt_template("assembly/asset_review_v1.md")
        rendered = self._render_prompt(template, {
            "asset_content": asset_content[:2000],
            "segment_descriptions": "\n".join(seg_descs),
            "visual_style": "(visual style guide not yet configured)",
            "keyframe_count": str(len(keyframes)),
        })

        # Encode keyframes as base64
        image_data_urls = []
        for idx, frame_path in keyframes:
            image_data_urls.append(self._encode_image_b64(frame_path))

        # Call the vision model
        base_url = review_config.get("vision_base_url", "https://openrouter.ai/api/v1")
        try:
            findings = self._call_vision_model(
                vision_model, base_url, api_key,
                rendered, image_data_urls,
            )
        except Exception as e:
            # Clean up keyframes
            import shutil
            shutil.rmtree(keyframe_dir, ignore_errors=True)
            return {
                "review_type": "visual",
                "status": "failed",
                "verdict": "issues_found",
                "summary": f"Vision API call failed: {str(e)[:200]}",
                "findings": {"error": str(e)[:500]},
            }

        # Clean up keyframe temp files
        import shutil
        shutil.rmtree(keyframe_dir, ignore_errors=True)

        verdict = findings.get("verdict", "issues_found")
        summary = findings.get("summary", "Visual inspection complete")

        # Save to DB
        review_id = self._save_review(
            asset_id=asset_id,
            media_id=media_id,
            media_path=video_path,
            review_type="visual",
            status="complete",
            verdict=verdict,
            findings=findings,
            summary=summary,
            model=vision_model,
            prompt_file="assembly/asset_review_v1.md",
            prompt_version=prompt_version,
        )

        # Log to provenance
        self._log_provenance(
            asset_id, "visual",
            f"Visual inspection: {verdict}. {summary}",
            verdict,
            model=vision_model,
            provider=review_config.get("vision_provider", "openrouter"),
            prompt_file="assembly/asset_review_v1.md",
            prompt_version=prompt_version,
            business_slug=business_slug,
        )

        return {
            "review_id": review_id,
            "review_type": "visual",
            "status": "complete",
            "verdict": verdict,
            "findings": findings,
            "summary": summary,
        }

    # ── ASSET-REVIEW-3: Audio inspection via whisper ─────────────────────

    def _extract_audio(self, video_path: str, output_path: str) -> bool:
        """Extract audio from a video file as 16kHz mono WAV for whisper."""
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0 and os.path.exists(output_path)

    def _transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio using faster-whisper (if available).

        Returns transcript text. Returns empty string if whisper not installed.
        """
        try:
            from faster_whisper import WhisperModel
            transcribe_config = self.models_config.get("transcription", {})
            model_name = transcribe_config.get("model", "medium")
            compute_type = transcribe_config.get("compute_type", "int8")
            language = transcribe_config.get("language", "en")

            model = WhisperModel(model_name, compute_type=compute_type)
            segments, info = model.transcribe(
                audio_path,
                language=language if language != "auto" else None,
                beam_size=5,
            )
            parts = [seg.text.strip() for seg in segments]
            return " ".join(parts)
        except ImportError:
            return ""  # faster-whisper not installed
        except Exception:
            return ""

    def _detect_looping(self, transcript: str) -> bool:
        """Detect if audio appears to loop.

        Heuristic: if the same 5+ word phrase appears 3+ times, flag as looping.
        This is a mechanical check on the transcript — the LLM is not involved.
        """
        if not transcript:
            return False
        words = transcript.split()
        if len(words) < 15:
            return False

        # Check for repeated 5-word phrases
        phrases = {}
        for i in range(len(words) - 4):
            phrase = " ".join(words[i:i+5]).lower()
            phrases[phrase] = phrases.get(phrase, 0) + 1

        for phrase, count in phrases.items():
            if count >= 3:
                return True
        return False

    def _script_has_vo_or_dialogue(self, asset_content: str, posts: str = None) -> bool:
        """Check if the script/content contains VO or spoken dialogue.

        Scans for VO markers, dialogue indicators, and spoken-content patterns
        that mean the output should have audio — not be silent.
        """
        text = (asset_content or "") + "\n" + (posts or "")
        if not text.strip():
            return False

        text_lower = text.lower()

        # Direct VO markers
        vo_markers = ["vo:", "voiceover:", "voice over:", "voice-over:", "narrator:"]
        for marker in vo_markers:
            if marker in text_lower:
                return True

        # Dialogue/speech indicators
        speech_markers = ["spoken:", "say:", "says:", "speaking:", "narrates:"]
        for marker in speech_markers:
            if marker in text_lower:
                return True

        # "Audio:" directives that aren't "audio: none" or "audio: silent"
        for line in text_lower.split("\n"):
            if line.strip().startswith("audio:") and "none" not in line and "silent" not in line:
                return True

        return False

    def run_audio_inspection(self, video_path: str, plan: dict,
                             asset_id: int, media_id: int,
                             business_slug: str = None,
                             asset_content: str = None,
                             asset_posts: str = None) -> dict:
        """ASSET-REVIEW-3: Audio inspection via whisper transcription.

        If the output has an audio stream:
        1. Extract audio
        2. Transcribe via faster-whisper
        3. Check for looping (repeated phrases)
        4. Check for unexpected audio (plan says no audio but audio has content)
        5. Check for silence when audio expected
        6. Cross-reference script: if script has VO/dialogue but plan has no
           audio strategy, flag as a silent failure
        """
        if not self._has_stream(video_path, "audio"):
            return {
                "review_type": "audio",
                "status": "complete",
                "verdict": "pass",
                "summary": "No audio stream in output — nothing to inspect",
                "findings": {"has_audio": False},
            }

        # Check if audio is silent
        is_silent = self._is_silent_audio(video_path)
        audio_block = plan.get("audio", {})
        original_audio = audio_block.get("original_audio", False)
        music = audio_block.get("music", {})
        music_ref = music.get("stock_ref") if music else None
        expects_sound = original_audio or bool(music_ref)

        if is_silent and not expects_sound:
            # Cross-reference: does the script have VO or dialogue that should
            # produce audio? If so, a silent output is a silent failure — the
            # plan's audio strategy doesn't match the content's requirements.
            script_has_vo = self._script_has_vo_or_dialogue(asset_content, asset_posts)
            vo_block = audio_block.get("vo", {})
            vo_take_id = vo_block.get("take_id", "") if vo_block else ""

            if script_has_vo and not vo_take_id and not music_ref:
                # Script has spoken content but plan has no VO take and no music
                # → the video will be silent despite having dialogue written
                warning = (
                    "Script contains VO/spoken dialogue but the plan has no VO take "
                    "and no music — the output is silent despite the script requiring audio. "
                    "Either generate a VO take or add background music."
                )
                findings = {
                    "has_audio": True, "is_silent": True, "expects_sound": False,
                    "script_has_vo": True, "vo_take_id": vo_take_id,
                    "warnings": [warning],
                }
                summary = "Script has VO but output is silent — no VO take or music in plan"
                review_id = self._save_review(
                    asset_id=asset_id, media_id=media_id, media_path=video_path,
                    review_type="audio", status="complete", verdict="issues_found",
                    findings=findings, summary=summary,
                )
                self._log_provenance(
                    asset_id, "audio",
                    f"Audio inspection: issues_found. {summary}",
                    "issues_found", business_slug=business_slug,
                )
                return {
                    "review_id": review_id,
                    "review_type": "audio",
                    "status": "complete",
                    "verdict": "issues_found",
                    "summary": summary,
                    "findings": findings,
                }

            review_id = self._save_review(
                asset_id=asset_id, media_id=media_id, media_path=video_path,
                review_type="audio", status="complete", verdict="pass",
                findings={"has_audio": True, "is_silent": True, "expects_sound": False},
                summary="Audio is silent as specified in the plan",
            )
            self._log_provenance(
                asset_id, "audio",
                "Audio inspection: pass. Audio is silent as specified in the plan",
                "pass", business_slug=business_slug,
            )
            return {
                "review_id": review_id,
                "review_type": "audio",
                "status": "complete",
                "verdict": "pass",
                "summary": "Audio is silent as specified in the plan",
                "findings": {"has_audio": True, "is_silent": True, "expects_sound": False},
            }

        if is_silent and expects_sound:
            review_id = self._save_review(
                asset_id=asset_id, media_id=media_id, media_path=video_path,
                review_type="audio", status="complete", verdict="issues_found",
                findings={"has_audio": True, "is_silent": True, "expects_sound": True},
                summary="Plan expects audio but output is silent",
            )
            self._log_provenance(
                asset_id, "audio",
                "Audio inspection: issues_found. Plan expects audio but output is silent",
                "issues_found", business_slug=business_slug,
            )
            return {
                "review_id": review_id,
                "review_type": "audio",
                "status": "complete",
                "verdict": "issues_found",
                "summary": "Plan expects audio but output is silent",
                "findings": {"has_audio": True, "is_silent": True, "expects_sound": True},
            }

        # Extract audio for transcription
        audio_dir = os.path.dirname(video_path)
        audio_extract_path = os.path.join(audio_dir, f"review_audio_{media_id}.wav")

        if not self._extract_audio(video_path, audio_extract_path):
            return {
                "review_type": "audio",
                "status": "failed",
                "verdict": "issues_found",
                "summary": "Could not extract audio for inspection",
                "findings": {"error": "audio extraction failed"},
            }

        # Transcribe
        transcript = self._transcribe_audio(audio_extract_path)

        # Clean up temp audio file
        try:
            os.remove(audio_extract_path)
        except OSError:
            pass

        findings = {
            "has_audio": True,
            "is_silent": False,
            "transcript": transcript[:500] if transcript else "",
            "transcript_word_count": len(transcript.split()) if transcript else 0,
            "expects_sound": expects_sound,
            "is_looping": False,
            "warnings": [],
        }

        # Check for looping
        if self._detect_looping(transcript):
            findings["is_looping"] = True
            findings["warnings"].append(
                "Audio appears to loop — the same phrase repeats 3+ times"
            )

        # Check for unexpected audio
        if not expects_sound and transcript:
            findings["warnings"].append(
                "Plan says no audio (original_audio=false, no music) but audio has speech content"
            )

        # Check for no speech when audio is non-silent
        if not transcript and not is_silent:
            findings["warnings"].append(
                "Audio is present and non-silent but no speech detected — likely ambient/looping"
            )

        verdict = "pass" if not findings["warnings"] else "issues_found"
        summary_parts = []
        if findings["is_looping"]:
            summary_parts.append("Audio is looping")
        if not transcript and not is_silent:
            summary_parts.append("No speech detected (ambient/looping)")
        if not expects_sound and transcript:
            summary_parts.append("Unexpected audio content")
        if not summary_parts:
            summary_parts.append("Audio inspection passed")
        summary = ". ".join(summary_parts)

        # Save to DB
        review_id = self._save_review(
            asset_id=asset_id,
            media_id=media_id,
            media_path=video_path,
            review_type="audio",
            status="complete",
            verdict=verdict,
            findings=findings,
            summary=summary,
        )

        self._log_provenance(
            asset_id, "audio",
            f"Audio inspection: {verdict}. {summary}",
            verdict, business_slug=business_slug,
        )

        return {
            "review_id": review_id,
            "review_type": "audio",
            "status": "complete",
            "verdict": verdict,
            "findings": findings,
            "summary": summary,
        }

    # ── ASSET-REVIEW-4: Content alignment aggregation ────────────────────

    def run_content_alignment(self, asset_id: int, media_id: int,
                              mechanical: dict = None,
                              visual: dict = None,
                              audio: dict = None,
                              business_slug: str = None,
                              asset_content: str = None,
                              asset_posts: str = None,
                              plan: dict = None) -> dict:
        """ASSET-REVIEW-4: LLM-based content alignment check.

        Uses an LLM to judge whether the final output is coherent given the
        script, plan, and all check results. Catches silent failures like
        "script has VO but plan has no audio strategy."
        """
        # Build a plan summary for the prompt
        plan_summary = "(no plan provided)"
        if plan:
            segments = plan.get("segments", [])
            audio_block = plan.get("audio", {})
            canvas = plan.get("canvas", {})
            seg_lines = []
            for i, seg in enumerate(segments):
                overlays = seg.get("overlays", [])
                caption = ""
                for ov in overlays:
                    if ov.get("type") == "caption" and ov.get("text"):
                        caption = ov["text"][:80]
                        break
                seg_lines.append(
                    f"  Seg {i+1}: source={seg.get('source','?')}, "
                    f"in={seg.get('in',0)}s, out={seg.get('out',0)}s"
                    f"{', caption: ' + caption if caption else ''}"
                )
            plan_summary = (
                f"Canvas: {json.dumps(canvas)}\n"
                f"Audio: {json.dumps(audio_block)}\n"
                f"Segments:\n" + "\n".join(seg_lines)
            )

        # Build the check result summaries
        mechanical_results = json.dumps(mechanical, indent=2) if mechanical else "(not run)"
        visual_results = (
            json.dumps(visual.get("findings", {}), indent=2)
            if visual and visual.get("status") == "complete"
            else "(not run or skipped)"
        )
        audio_results = (
            json.dumps(audio.get("findings", {}), indent=2)
            if audio and audio.get("status") == "complete"
            else "(not run)"
        )

        # Try LLM-based alignment check
        review_config = self.models_config.get("asset_review", {})
        enabled = review_config.get("enabled", True)
        vision_model = review_config.get("vision_model")
        api_key_env = review_config.get("vision_api_key_env", "OPENROUTER_API_KEY")
        api_key = os.environ.get(api_key_env, "")

        full_content = (asset_content or "") + "\n" + (asset_posts or "")

        if enabled and vision_model and api_key:
            # Load and render the alignment prompt
            try:
                template, prompt_version = self._load_prompt_template(
                    "assembly/asset_alignment_v1.md")
                rendered = self._render_prompt(template, {
                    "asset_content": full_content[:3000],
                    "plan_summary": plan_summary,
                    "mechanical_results": mechanical_results[:2000],
                    "visual_results": visual_results[:2000],
                    "audio_results": audio_results[:2000],
                })

                base_url = review_config.get("vision_base_url", "https://openrouter.ai/api/v1")
                # Text-only call — no images needed for alignment
                findings = self._call_vision_model(
                    vision_model, base_url, api_key,
                    rendered, [],
                )

                verdict = findings.get("verdict", "needs_operator_decision")
                summary = findings.get("summary", "Content alignment check complete")
                issues = findings.get("issues", [])

                review_id = self._save_review(
                    asset_id=asset_id, media_id=media_id, media_path="",
                    review_type="alignment", status="complete",
                    verdict=verdict, findings=findings, summary=summary,
                    model=vision_model,
                    prompt_file="assembly/asset_alignment_v1.md",
                    prompt_version=prompt_version,
                )

                self._log_provenance(
                    asset_id, "alignment",
                    f"Content alignment: {verdict}. {summary}",
                    verdict,
                    model=vision_model,
                    provider=review_config.get("vision_provider", "openrouter"),
                    prompt_file="assembly/asset_alignment_v1.md",
                    prompt_version=prompt_version,
                    business_slug=business_slug,
                )

                return {
                    "review_id": review_id,
                    "review_type": "alignment",
                    "status": "complete",
                    "verdict": verdict,
                    "findings": findings,
                    "summary": summary,
                }
            except Exception as e:
                # LLM call failed — fall through to mechanical aggregation
                pass

        # Fallback: mechanical aggregation (no LLM)
        # This also includes the script-audio coherence check
        issues = []
        verdict = "ready_for_operator"

        if mechanical:
            for w in mechanical.get("warnings", []):
                issues.append({
                    "severity": "medium",
                    "category": "mechanical",
                    "description": w,
                    "source": "mechanical",
                })

        if visual and visual.get("status") == "complete":
            if visual.get("verdict") == "issues_found":
                for issue in visual.get("findings", {}).get("issues", []):
                    issues.append({
                        "severity": issue.get("severity", "medium"),
                        "category": issue.get("category", "visual"),
                        "description": issue.get("description", ""),
                        "source": "visual",
                        "recommended_action": issue.get("recommended_action", ""),
                    })

        if audio and audio.get("status") == "complete":
            if audio.get("verdict") == "issues_found":
                for w in audio.get("findings", {}).get("warnings", []):
                    issues.append({
                        "severity": "high" if "loop" in w.lower() else "medium",
                        "category": "audio",
                        "description": w,
                        "source": "audio",
                    })

        # Script-audio coherence check (even without LLM)
        if asset_content or asset_posts:
            script_has_vo = self._script_has_vo_or_dialogue(asset_content, asset_posts)
            if plan:
                audio_block = plan.get("audio", {})
                vo_block = audio_block.get("vo", {})
                vo_take_id = vo_block.get("take_id", "") if vo_block else ""
                music = audio_block.get("music", {})
                music_ref = music.get("stock_ref") if music else None
                if script_has_vo and not vo_take_id and not music_ref:
                    issues.append({
                        "severity": "high",
                        "category": "audio_coherence",
                        "description": (
                            "Script contains VO/spoken dialogue but the plan has no VO take "
                            "and no music — output will be silent despite dialogue"
                        ),
                        "source": "alignment",
                        "recommended_action": "Generate a VO take or add background music",
                    })

        # Determine overall verdict
        high_issues = [i for i in issues if i.get("severity") == "high"]
        if high_issues:
            verdict = "needs_rerender"
        elif issues:
            verdict = "needs_operator_decision"

        summary_parts = []
        if not issues:
            summary_parts.append("All checks passed — ready for your review")
        else:
            for issue in issues:
                summary_parts.append(f"{issue['severity'].upper()}: {issue['description']}")
        summary = ". ".join(summary_parts[:5])

        findings = {
            "verdict": verdict,
            "issues": issues,
            "mechanical_verdict": mechanical.get("verdict") if mechanical else None,
            "visual_verdict": visual.get("verdict") if visual else None,
            "audio_verdict": audio.get("verdict") if audio else None,
            "issue_count": len(issues),
            "llm_used": False,
        }

        review_id = self._save_review(
            asset_id=asset_id, media_id=media_id, media_path="",
            review_type="alignment", status="complete",
            verdict=verdict, findings=findings, summary=summary,
        )

        self._log_provenance(
            asset_id, "alignment",
            f"Content alignment: {verdict}. {summary}",
            verdict, business_slug=business_slug,
        )

        return {
            "review_id": review_id,
            "review_type": "alignment",
            "status": "complete",
            "verdict": verdict,
            "findings": findings,
            "summary": summary,
        }

    # ── ASSET-REVIEW-6: Image review ─────────────────────────────────────

    def run_image_review(self, image_path: str, prompt: str,
                         asset_content: str, asset_id: int,
                         media_id: int, business_slug: str = None) -> dict:
        """ASSET-REVIEW-6: Lightweight vision check on standalone images.

        1. Mechanical: file exists, size > 10KB, correct aspect ratio
        2. Visual: vision LLM examines the image vs the prompt that generated it
        3. Content: does the image match the asset content?

        This is lighter-weight than the video review (single image, no audio).
        """
        # Mechanical checks
        checks = {
            "file_exists": os.path.exists(image_path),
            "file_size_kb": 0,
            "is_image": image_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")),
            "warnings": [],
        }

        if checks["file_exists"]:
            checks["file_size_kb"] = round(os.path.getsize(image_path) / 1024, 1)
            if checks["file_size_kb"] < 10:
                checks["warnings"].append(f"Image is only {checks['file_size_kb']}KB — may be low quality")

        if not checks["file_exists"]:
            checks["warnings"].append("Image file does not exist")

        # Vision check (if configured)
        review_config = self.models_config.get("asset_review", {})
        enabled = review_config.get("enabled", True)
        vision_model = review_config.get("vision_model")
        api_key_env = review_config.get("vision_api_key_env", "OPENROUTER_API_KEY")
        api_key = os.environ.get(api_key_env, "")

        vision_findings = None
        if enabled and vision_model and api_key and checks["file_exists"]:
            # Build a simple prompt for image review
            text_prompt = (
                f"You are reviewing an AI-generated image. Does it match the prompt that generated it?\n\n"
                f"Prompt: {prompt[:500]}\n\n"
                f"Asset content context: {asset_content[:500]}\n\n"
                f"Check: Does the image show what the prompt describes? "
                f"Are there obvious AI artifacts or quality issues?\n\n"
                f"Respond with ONLY valid JSON:\n"
                f'{{"verdict": "pass" | "issues_found", '
                f'"issues": [{{"severity": "high" | "medium" | "low", '
                f'"description": "...", "recommended_action": "..."}}], '
                f'"summary": "..."}}'
            )

            try:
                image_data_url = self._encode_image_b64(image_path)
                base_url = review_config.get("vision_base_url", "https://openrouter.ai/api/v1")
                vision_findings = self._call_vision_model(
                    vision_model, base_url, api_key,
                    text_prompt, [image_data_url],
                )
            except Exception as e:
                vision_findings = {"verdict": "issues_found", "issues": [], "summary": f"Vision API failed: {str(e)[:200]}"}

        # Combine mechanical + vision
        all_warnings = list(checks["warnings"])
        if vision_findings:
            for issue in vision_findings.get("issues", []):
                all_warnings.append(f"{issue.get('severity','?').upper()}: {issue.get('description','')}")

        verdict = "pass" if not all_warnings else "issues_found"

        summary_parts = []
        if checks["file_size_kb"] > 0:
            summary_parts.append(f"Image: {checks['file_size_kb']}KB")
        if vision_findings:
            summary_parts.append(vision_findings.get("summary", "Vision check complete"))
        if all_warnings and not vision_findings:
            summary_parts.extend(all_warnings)
        if not summary_parts:
            summary_parts.append("Image review complete")
        summary = ". ".join(summary_parts[:4])

        findings = {
            "mechanical": checks,
            "vision": vision_findings,
            "prompt": prompt[:200] if prompt else "",
        }

        model_name = vision_model if vision_findings else "mechanical"
        prompt_file = "assembly/asset_review_v1.md" if vision_findings else None
        prompt_ver = "1.0" if vision_findings else None

        review_id = self._save_review(
            asset_id=asset_id,
            media_id=media_id,
            media_path=image_path,
            review_type="image",
            status="complete",
            verdict=verdict,
            findings=findings,
            summary=summary,
            model=model_name,
            prompt_file=prompt_file,
            prompt_version=prompt_ver,
        )

        self._log_provenance(
            asset_id, "image",
            f"Image review: {verdict}. {summary}",
            verdict,
            model=model_name,
            provider=review_config.get("vision_provider", "openrouter") if vision_findings else "local",
            prompt_file=prompt_file or "(asset_review)",
            prompt_version=prompt_ver or "1.0",
            business_slug=business_slug,
        )

        return {
            "review_id": review_id,
            "review_type": "image",
            "status": "complete",
            "verdict": verdict,
            "findings": findings,
            "summary": summary,
        }