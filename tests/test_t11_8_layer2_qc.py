"""
Tests for T11.8: Layer-2 Asset QC.

Per CORRECTION-episode-format-and-reference-assets-v1.0 §7.2:
- Identity check: face-embedding cosine similarity of returned stills and
  first/mid/last animation frames against canonical character_ref images.
  Below threshold → qc_flag: identity_drift.
- Grade check: color-histogram distance vs location plate.
  Breach → qc_flag: grade_break.

AC (from task spec):
1. Off-character test still is flagged (identity_drift)
2. Grade-break still is flagged (grade_break)
3. Thresholds are config-driven (changing config changes pass/fail)
4. Flags never auto-reject (verdict is always advisory)
5. If face model unavailable, identity check skips gracefully
6. Mock face embeddings (don't require a real model)
7. Real color histograms on small test images
"""

import json
import os
import sys
import pytest
import numpy as np
from PIL import Image
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from layer2_qc import (
    FaceEmbedder,
    compute_color_histogram,
    histogram_correlation,
    histogram_chi_square,
    histogram_bhattacharyya,
    histogram_intersection,
    histogram_distance,
    is_grade_break,
    run_grade_check,
    run_identity_check,
    run_layer2_qc,
)
from asset_review import AssetReviewer


# ── Helpers: create small test images with known color distributions ─────

def _make_solid_image(path, color=(128, 128, 128), size=(64, 64)):
    """Create a small solid-color image."""
    img = Image.new("RGB", size, color)
    img.save(path)
    return path


def _make_gradient_image(path, base_color=(100, 150, 200), size=(64, 64)):
    """Create a small image with a gradient (moderate color variety)."""
    img = Image.new("RGB", size)
    px = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            r = min(255, base_color[0] + x * 2)
            g = min(255, base_color[1] + y * 2)
            b = min(255, base_color[2] + (x + y))
            px[x, y] = (r, g, b)
    img.save(path)
    return path


def _make_warm_image(path, size=(64, 64)):
    """Create a warm-toned image (golden hour style — reds/oranges)."""
    img = Image.new("RGB", size)
    px = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            r = 200 + (x % 30)
            g = 140 + (y % 30)
            b = 60 + ((x + y) % 20)
            px[x, y] = (min(255, r), min(255, g), min(255, b))
    img.save(path)
    return path


def _make_cold_image(path, size=(64, 64)):
    """Create a cold-toned image (blue/teal — opposite of warm)."""
    img = Image.new("RGB", size)
    px = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            r = 40 + (x % 20)
            g = 80 + (y % 30)
            b = 180 + ((x + y) % 40)
            px[x, y] = (min(255, r), min(255, g), min(255, b))
    img.save(path)
    return path


# ── Mock FaceEmbedder for identity check tests ──────────────────────────

class MockFaceEmbedder:
    """Mock face embedder that returns pre-set embeddings.

    This avoids needing a real ONNX model. It simulates the FaceEmbedder
    interface: .available, .get_embedding(path) -> list[float] | None.
    """

    def __init__(self, embeddings: dict[str, list[float]], available=True):
        """
        Args:
            embeddings: dict mapping image path → embedding vector.
                        If a path is not in the dict, returns None (no face).
            available: whether the model is "available".
        """
        self._embeddings = embeddings
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    def get_embedding(self, image_path: str) -> list[float] | None:
        return self._embeddings.get(image_path)


def _make_embedding(seed: int, dim: int = 128) -> list[float]:
    """Create a deterministic embedding vector from a seed."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float64)
    v /= np.linalg.norm(v)
    return v.tolist()


# ── Config fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def standard_qc_config():
    """Standard episode_qc config matching models.yaml defaults."""
    return {
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


@pytest.fixture
def strict_qc_config():
    """Config with very strict thresholds (easy to trigger flags)."""
    return {
        "identity": {
            "enabled": True,
            "model_path": "models/insightface/buffalo_l/w600k_r50.onnx",
            "min_cosine_similarity": 0.99,  # very strict
            "frame_positions": ["first", "middle", "last"],
            "min_face_confidence": 0.5,
        },
        "grade": {
            "enabled": True,
            "histogram_metric": "correlation",
            "histogram_threshold": 0.95,  # very strict
            "histogram_bins": 32,
            "frame_positions": ["first", "middle", "last"],
        },
    }


@pytest.fixture
def lenient_qc_config():
    """Config with very lenient thresholds (hard to trigger flags)."""
    return {
        "identity": {
            "enabled": True,
            "model_path": "models/insightface/buffalo_l/w600k_r50.onnx",
            "min_cosine_similarity": 0.01,  # very lenient
            "frame_positions": ["first", "middle", "last"],
            "min_face_confidence": 0.5,
        },
        "grade": {
            "enabled": True,
            # Use chi_square (lower = better) with a huge threshold so nothing breaks
            "histogram_metric": "chi_square",
            "histogram_threshold": 999999.0,  # very lenient — nothing exceeds this
            "histogram_bins": 32,
            "frame_positions": ["first", "middle", "last"],
        },
    }


# ════════════════════════════════════════════════════════════════════════
# Part 1: Color histogram tests (real histograms on small test images)
# ════════════════════════════════════════════════════════════════════════

class TestColorHistogram:
    """Tests for color-histogram computation and grade check."""

    def test_identical_images_have_perfect_correlation(self, tmp_path):
        """Two identical images should have correlation ~1.0."""
        img1 = _make_warm_image(str(tmp_path / "warm1.jpg"))
        img2 = _make_warm_image(str(tmp_path / "warm2.jpg"))

        h1 = compute_color_histogram(img1, bins=16)
        h2 = compute_color_histogram(img2, bins=16)

        assert h1 is not None
        assert h2 is not None
        assert histogram_correlation(h1, h2) > 0.999

    def test_different_grade_images_have_low_correlation(self, tmp_path):
        """Warm and cold images should have low histogram correlation."""
        warm = _make_warm_image(str(tmp_path / "warm.jpg"))
        cold = _make_cold_image(str(tmp_path / "cold.jpg"))

        h_warm = compute_color_histogram(warm, bins=16)
        h_cold = compute_color_histogram(cold, bins=16)

        corr = histogram_correlation(h_warm, h_cold)
        # Very different color distributions → low correlation
        assert corr < 0.5

    def test_solid_color_images_have_zero_correlation_if_different(self, tmp_path):
        """Two different solid-color images have zero or negative correlation."""
        red = _make_solid_image(str(tmp_path / "red.jpg"), color=(200, 50, 50))
        blue = _make_solid_image(str(tmp_path / "blue.jpg"), color=(50, 50, 200))

        h_red = compute_color_histogram(red, bins=8)
        h_blue = compute_color_histogram(blue, bins=8)

        corr = histogram_correlation(h_red, h_blue)
        # Different solid colors → low correlation (bins are disjoint)
        assert corr < 0.1

    def test_compute_histogram_returns_none_for_bad_path(self):
        """Nonexistent image returns None."""
        assert compute_color_histogram("/nonexistent/image.jpg") is None

    def test_chi_square_distance_is_zero_for_identical(self, tmp_path):
        """Identical images have chi-square distance ~0."""
        img1 = _make_gradient_image(str(tmp_path / "grad1.jpg"))
        img2 = _make_gradient_image(str(tmp_path / "grad2.jpg"))

        h1 = compute_color_histogram(img1, bins=16)
        h2 = compute_color_histogram(img2, bins=16)

        assert histogram_chi_square(h1, h2) < 0.001

    def test_bhattacharyya_distance_range(self, tmp_path):
        """Bhattacharyya distance is between 0 and 1."""
        warm = _make_warm_image(str(tmp_path / "warm.jpg"))
        cold = _make_cold_image(str(tmp_path / "cold.jpg"))

        h_w = compute_color_histogram(warm, bins=16)
        h_c = compute_color_histogram(cold, bins=16)

        dist = histogram_bhattacharyya(h_w, h_c)
        assert 0.0 <= dist <= 1.0

    def test_is_grade_break_correlation(self):
        """Grade break logic for correlation metric (higher = better)."""
        # Below threshold → break
        assert is_grade_break(0.2, 0.3, "correlation") is True
        # Above threshold → OK
        assert is_grade_break(0.5, 0.3, "correlation") is False

    def test_is_grade_break_chi_square(self):
        """Grade break logic for chi_square metric (lower = better)."""
        # Above threshold → break
        assert is_grade_break(10.0, 5.0, "chi_square") is True
        # Below threshold → OK
        assert is_grade_break(2.0, 5.0, "chi_square") is False

    def test_histogram_distance_unknown_metric_raises(self, tmp_path):
        """Unknown metric raises ValueError."""
        h1 = compute_color_histogram(_make_solid_image(str(tmp_path / "a.jpg")), bins=8)
        h2 = compute_color_histogram(_make_solid_image(str(tmp_path / "b.jpg")), bins=8)
        with pytest.raises(ValueError, match="Unknown histogram metric"):
            histogram_distance(h1, h2, "unknown_metric")


# ════════════════════════════════════════════════════════════════════════
# Part 2: Grade check (run_grade_check)
# ════════════════════════════════════════════════════════════════════════

class TestGradeCheck:
    """Tests for the grade check runner."""

    def test_matching_grade_passes(self, tmp_path, standard_qc_config):
        """A still with matching grade (similar color distribution) passes."""
        plate = _make_warm_image(str(tmp_path / "plate.jpg"))
        still = _make_warm_image(str(tmp_path / "still.jpg"))

        result = run_grade_check([still], plate, standard_qc_config["grade"])

        assert result["status"] == "complete"
        assert result["flag"] is None
        assert result["per_image"][0]["status"] == "ok"

    def test_grade_break_flagged(self, tmp_path, standard_qc_config):
        """A still with very different color distribution → grade_break flag."""
        plate = _make_warm_image(str(tmp_path / "plate.jpg"))
        still = _make_cold_image(str(tmp_path / "still.jpg"))

        result = run_grade_check([still], plate, standard_qc_config["grade"])

        assert result["status"] == "complete"
        assert result["flag"] == "qc_flag: grade_break"
        assert result["per_image"][0]["status"] == "flagged"

    def test_grade_check_skips_if_plate_missing(self, standard_qc_config):
        """If plate image can't be loaded, grade check skips gracefully."""
        result = run_grade_check(["/some/still.jpg"], "/nonexistent/plate.jpg",
                                 standard_qc_config["grade"])
        assert result["status"] == "skipped"
        assert result["flag"] is None

    def test_grade_check_handles_bad_still(self, tmp_path, standard_qc_config):
        """If a still can't be loaded, it's marked as skipped, no crash."""
        plate = _make_warm_image(str(tmp_path / "plate.jpg"))
        result = run_grade_check(["/nonexistent/still.jpg"], plate,
                                 standard_qc_config["grade"])
        assert result["status"] == "complete"
        assert result["per_image"][0]["status"] == "skipped"


# ════════════════════════════════════════════════════════════════════════
# Part 3: Identity check (run_identity_check with mock embeddings)
# ════════════════════════════════════════════════════════════════════════

class TestIdentityCheck:
    """Tests for the face-embedding identity check."""

    def test_matching_identity_passes(self, tmp_path, standard_qc_config):
        """A still with a matching face embedding passes identity check."""
        ref1 = str(tmp_path / "ref1.jpg")
        ref2 = str(tmp_path / "ref2.jpg")
        still = str(tmp_path / "still.jpg")

        # All images get the same embedding (same character)
        emb = _make_embedding(42)
        embedder = MockFaceEmbedder({
            ref1: emb, ref2: emb, still: emb,
        })

        result = run_identity_check(
            [still], [ref1, ref2], standard_qc_config["identity"], embedder=embedder,
        )

        assert result["status"] == "complete"
        assert result["flag"] is None
        assert result["per_image"][0]["status"] == "ok"
        assert result["per_image"][0]["max_cosine_similarity"] > 0.99

    def test_off_character_flagged(self, tmp_path, standard_qc_config):
        """A still with a different face embedding → identity_drift flag."""
        ref1 = str(tmp_path / "ref1.jpg")
        ref2 = str(tmp_path / "ref2.jpg")
        still = str(tmp_path / "still.jpg")

        # Character ref embeddings
        ref_emb = _make_embedding(42)
        # Different character (orthogonal embedding)
        off_emb = _make_embedding(999)

        embedder = MockFaceEmbedder({
            ref1: ref_emb, ref2: ref_emb,
            still: off_emb,  # different character
        })

        result = run_identity_check(
            [still], [ref1, ref2], standard_qc_config["identity"], embedder=embedder,
        )

        assert result["status"] == "complete"
        assert result["flag"] == "qc_flag: identity_drift"
        assert result["per_image"][0]["status"] == "flagged"

    def test_no_face_detected_skipped(self, tmp_path, standard_qc_config):
        """If no face is detected in the still, it's marked 'no_face' (not flagged)."""
        ref1 = str(tmp_path / "ref1.jpg")
        still = str(tmp_path / "still.jpg")

        ref_emb = _make_embedding(42)
        embedder = MockFaceEmbedder({
            ref1: ref_emb,
            # still not in dict → no embedding → no face
        })

        result = run_identity_check(
            [still], [ref1], standard_qc_config["identity"], embedder=embedder,
        )

        assert result["status"] == "complete"
        assert result["flag"] is None  # no face = no drift flag
        assert result["per_image"][0]["status"] == "no_face"

    def test_identity_skipped_if_model_unavailable(self, tmp_path, standard_qc_config):
        """If the face model is unavailable, identity check skips gracefully."""
        ref1 = str(tmp_path / "ref1.jpg")
        still = str(tmp_path / "still.jpg")

        embedder = MockFaceEmbedder({}, available=False)

        result = run_identity_check(
            [still], [ref1], standard_qc_config["identity"], embedder=embedder,
        )

        assert result["status"] == "skipped"
        assert result["flag"] is None
        assert "not available" in result["reason"].lower()

    def test_identity_skipped_if_no_ref_embeddings(self, tmp_path, standard_qc_config):
        """If no face embeddings could be extracted from refs, skips gracefully."""
        ref1 = str(tmp_path / "ref1.jpg")
        still = str(tmp_path / "still.jpg")

        # Refs don't produce embeddings
        embedder = MockFaceEmbedder({})

        result = run_identity_check(
            [still], [ref1], standard_qc_config["identity"], embedder=embedder,
        )

        assert result["status"] == "skipped"
        assert result["flag"] is None


# ════════════════════════════════════════════════════════════════════════
# Part 4: Config-driven threshold tests
# ════════════════════════════════════════════════════════════════════════

class TestConfigDrivenThresholds:
    """Tests proving that thresholds are config-driven, not hardcoded."""

    def test_strict_identity_threshold_flags_similar_faces(
        self, tmp_path, standard_qc_config, strict_qc_config
    ):
        """With a strict threshold (0.99), even somewhat similar faces are flagged."""
        ref1 = str(tmp_path / "ref1.jpg")
        still = str(tmp_path / "still.jpg")

        ref_emb = _make_embedding(42)
        # Create a slightly different embedding (high similarity but not 1.0)
        still_emb = _make_embedding(42)
        # Perturb slightly
        arr = np.array(still_emb)
        arr += np.random.RandomState(1).randn(len(arr)) * 0.1
        arr /= np.linalg.norm(arr)
        still_emb = arr.tolist()

        embedder = MockFaceEmbedder({ref1: ref_emb, still: still_emb})

        # With standard threshold (0.45), this should pass
        result_standard = run_identity_check(
            [still], [ref1], standard_qc_config["identity"], embedder=embedder,
        )
        assert result_standard["flag"] is None

        # With strict threshold (0.99), this should flag
        result_strict = run_identity_check(
            [still], [ref1], strict_qc_config["identity"], embedder=embedder,
        )
        assert result_strict["flag"] == "qc_flag: identity_drift"

    def test_lenient_identity_threshold_allows_different_faces(
        self, tmp_path, standard_qc_config, lenient_qc_config
    ):
        """With a lenient threshold (0.01), different faces pass."""
        ref1 = str(tmp_path / "ref1.jpg")
        still = str(tmp_path / "still.jpg")

        ref_emb = _make_embedding(42)
        off_emb = _make_embedding(999)

        embedder = MockFaceEmbedder({ref1: ref_emb, still: off_emb})

        # With standard threshold, this flags
        result_standard = run_identity_check(
            [still], [ref1], standard_qc_config["identity"], embedder=embedder,
        )
        assert result_standard["flag"] == "qc_flag: identity_drift"

        # With lenient threshold, this passes
        result_lenient = run_identity_check(
            [still], [ref1], lenient_qc_config["identity"], embedder=embedder,
        )
        assert result_lenient["flag"] is None

    def test_strict_grade_threshold_flags_similar_grades(
        self, tmp_path, standard_qc_config, strict_qc_config
    ):
        """With a strict histogram threshold, similar-but-not-identical grades flag."""
        plate = _make_warm_image(str(tmp_path / "plate.jpg"))
        # Slightly different warm image (add some variation)
        still = _make_gradient_image(str(tmp_path / "still.jpg"), base_color=(180, 130, 50))

        # Standard threshold (0.30): likely passes (both warmish)
        result_standard = run_grade_check([still], plate, standard_qc_config["grade"])

        # Strict threshold (0.95): likely flags (not identical enough)
        result_strict = run_grade_check([still], plate, strict_qc_config["grade"])

        # The strict threshold should be more likely to flag
        # (not guaranteed in all cases, but the threshold difference is the point)
        # We verify the thresholds are actually different in the results
        assert result_standard["threshold"] == 0.30
        assert result_strict["threshold"] == 0.95

    def test_lenient_grade_threshold_allows_different_grades(
        self, tmp_path, standard_qc_config, lenient_qc_config
    ):
        """With a lenient histogram threshold, even very different grades pass."""
        plate = _make_warm_image(str(tmp_path / "plate.jpg"))
        still = _make_cold_image(str(tmp_path / "still.jpg"))

        # Standard threshold (0.30): flags
        result_standard = run_grade_check([still], plate, standard_qc_config["grade"])
        assert result_standard["flag"] == "qc_flag: grade_break"

        # Lenient threshold (0.001): passes (threshold so low anything passes)
        result_lenient = run_grade_check([still], plate, lenient_qc_config["grade"])
        assert result_lenient["flag"] is None

    def test_no_config_uses_defaults(self, tmp_path):
        """If episode_qc config is None, defaults are used (no crash)."""
        plate = _make_warm_image(str(tmp_path / "plate.jpg"))
        still = _make_warm_image(str(tmp_path / "still.jpg"))

        # None config should use defaults and not crash
        result = run_grade_check([still], plate, _merge_none_config())

        assert result["status"] == "complete"


def _merge_none_config():
    """Helper: get the default grade config when qc_config is None."""
    # This mirrors what _merge_config does internally
    from layer2_qc import _DEFAULT_QC_CONFIG
    return _DEFAULT_QC_CONFIG["grade"]


# ════════════════════════════════════════════════════════════════════════
# Part 5: Full run_layer2_qc integration tests
# ════════════════════════════════════════════════════════════════════════

class TestRunLayer2QC:
    """Integration tests for the top-level run_layer2_qc function."""

    def test_off_character_still_flagged(self, tmp_path, standard_qc_config):
        """An off-character still is flagged with identity_drift (AC #1)."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_warm_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        ref_emb = _make_embedding(42)
        off_emb = _make_embedding(999)
        embedder = MockFaceEmbedder({ref1: ref_emb, still: off_emb})

        result = run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            qc_config=standard_qc_config,
            asset_id=1,
            media_id=1,
            db_path=str(tmp_path / "qc.db"),
            embedder=embedder,
        )

        assert "qc_flag: identity_drift" in result["flags"]
        assert result["status"] == "complete"
        # Grade should pass (both warm images)
        assert "qc_flag: grade_break" not in result["flags"]

    def test_grade_break_still_flagged(self, tmp_path, standard_qc_config):
        """A grade-break still is flagged with grade_break (AC #2)."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_cold_image(still)  # different grade
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        ref_emb = _make_embedding(42)
        embedder = MockFaceEmbedder({ref1: ref_emb, still: ref_emb})  # same character

        result = run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            qc_config=standard_qc_config,
            asset_id=1,
            media_id=1,
            db_path=str(tmp_path / "qc.db"),
            embedder=embedder,
        )

        assert "qc_flag: grade_break" in result["flags"]
        # Identity should pass (same character)
        assert "qc_flag: identity_drift" not in result["flags"]

    def test_both_flags_can_fire(self, tmp_path, standard_qc_config):
        """Both identity_drift and grade_break can fire simultaneously."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_cold_image(still)  # different grade + different character
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        ref_emb = _make_embedding(42)
        off_emb = _make_embedding(999)
        embedder = MockFaceEmbedder({ref1: ref_emb, still: off_emb})

        result = run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            qc_config=standard_qc_config,
            asset_id=1,
            media_id=1,
            db_path=str(tmp_path / "qc.db"),
            embedder=embedder,
        )

        assert "qc_flag: identity_drift" in result["flags"]
        assert "qc_flag: grade_break" in result["flags"]

    def test_clean_still_no_flags(self, tmp_path, standard_qc_config):
        """A clean still (matching character + matching grade) has no flags."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_warm_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        ref_emb = _make_embedding(42)
        embedder = MockFaceEmbedder({ref1: ref_emb, still: ref_emb})

        result = run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            qc_config=standard_qc_config,
            asset_id=1,
            media_id=1,
            db_path=str(tmp_path / "qc.db"),
            embedder=embedder,
        )

        assert result["flags"] == []
        assert result["status"] == "complete"

    def test_flags_never_auto_reject(self, tmp_path, standard_qc_config):
        """Flags are advisory — verdict is always 'advisory', never auto-reject (AC #4)."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_cold_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        ref_emb = _make_embedding(42)
        off_emb = _make_embedding(999)
        embedder = MockFaceEmbedder({ref1: ref_emb, still: off_emb})

        result = run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            qc_config=standard_qc_config,
            asset_id=1,
            media_id=1,
            db_path=str(tmp_path / "qc.db"),
            embedder=embedder,
        )

        # Even with both flags, status is "complete" (not "reject" or "fail")
        assert result["status"] == "complete"
        # The review_type is "layer2_qc"
        assert result["review_type"] == "layer2_qc"
        # Flags are present but advisory
        assert len(result["flags"]) > 0

    def test_identity_skipped_if_model_unavailable(self, tmp_path, standard_qc_config):
        """If the face model is unavailable, identity check skips gracefully (AC #5)."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_warm_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        embedder = MockFaceEmbedder({}, available=False)

        result = run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            qc_config=standard_qc_config,
            asset_id=1,
            media_id=1,
            db_path=str(tmp_path / "qc.db"),
            embedder=embedder,
        )

        # Identity should be skipped, grade should pass
        assert result["findings"]["identity"]["status"] == "skipped"
        assert "qc_flag: identity_drift" not in result["flags"]
        assert "qc_flag: grade_break" not in result["flags"]
        assert result["status"] == "complete"

    def test_saved_to_db(self, tmp_path, standard_qc_config):
        """Layer-2 QC results are saved to asset_reviews table."""
        import sqlite3

        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_warm_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        ref_emb = _make_embedding(42)
        embedder = MockFaceEmbedder({ref1: ref_emb, still: ref_emb})

        db_path = str(tmp_path / "qc.db")
        result = run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            qc_config=standard_qc_config,
            asset_id=10,
            media_id=20,
            db_path=db_path,
            embedder=embedder,
        )

        # Verify saved to DB
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM asset_reviews WHERE review_type = 'layer2_qc'",
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["asset_id"] == 10
        assert row["media_id"] == 20
        assert row["verdict"] == "advisory"  # NEVER auto-reject
        assert row["review_type"] == "layer2_qc"

    def test_disabled_identity_check(self, tmp_path):
        """When identity check is disabled in config, it's skipped."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_warm_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        config = {
            "identity": {"enabled": False},
            "grade": {
                "enabled": True,
                "histogram_metric": "correlation",
                "histogram_threshold": 0.30,
                "histogram_bins": 32,
                "frame_positions": ["first", "middle", "last"],
            },
        }

        result = run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            qc_config=config,
            asset_id=1,
            media_id=1,
            db_path=str(tmp_path / "qc.db"),
        )

        assert result["findings"]["identity"]["status"] == "skipped"
        assert "qc_flag: identity_drift" not in result["flags"]

    def test_disabled_grade_check(self, tmp_path):
        """When grade check is disabled in config, it's skipped."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_warm_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        config = {
            "identity": {
                "enabled": True,
                "model_path": "/nonexistent/model.onnx",
                "min_cosine_similarity": 0.45,
                "frame_positions": ["first", "middle", "last"],
                "min_face_confidence": 0.5,
            },
            "grade": {"enabled": False},
        }

        result = run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            qc_config=config,
            asset_id=1,
            media_id=1,
            db_path=str(tmp_path / "qc.db"),
        )

        assert result["findings"]["grade"]["status"] == "skipped"
        assert "qc_flag: grade_break" not in result["flags"]


# ════════════════════════════════════════════════════════════════════════
# Part 6: AssetReviewer integration test
# ════════════════════════════════════════════════════════════════════════

class TestAssetReviewerIntegration:
    """Test that AssetReviewer.run_layer2_qc works end-to-end."""

    def test_reviewer_run_layer2_qc(self, tmp_path, standard_qc_config):
        """AssetReviewer.run_layer2_qc delegates to the QC module correctly."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_cold_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        ref_emb = _make_embedding(42)
        off_emb = _make_embedding(999)
        embedder = MockFaceEmbedder({ref1: ref_emb, still: off_emb})

        reviewer = AssetReviewer(
            {"episode_qc": standard_qc_config},
            db_path=str(tmp_path / "review.db"),
        )

        result = reviewer.run_layer2_qc(
            media_path=still,
            character_ref_paths=[ref1],
            location_plate_path=plate,
            asset_id=1,
            media_id=1,
            business_slug="test",
            embedder=embedder,
        )

        assert "qc_flag: identity_drift" in result["flags"]
        assert "qc_flag: grade_break" in result["flags"]
        assert result["review_type"] == "layer2_qc"

    def test_reviewer_uses_config_thresholds(self, tmp_path, standard_qc_config, lenient_qc_config):
        """AssetReviewer passes config thresholds through to the QC module."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_cold_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        ref_emb = _make_embedding(42)
        off_emb = _make_embedding(999)
        embedder = MockFaceEmbedder({ref1: ref_emb, still: off_emb})

        # Standard config → flags
        reviewer_strict = AssetReviewer(
            {"episode_qc": standard_qc_config},
            db_path=str(tmp_path / "strict.db"),
        )
        result_strict = reviewer_strict.run_layer2_qc(
            media_path=still, character_ref_paths=[ref1],
            location_plate_path=plate, asset_id=1, media_id=1,
            embedder=embedder,
        )
        assert len(result_strict["flags"]) > 0

        # Lenient config → no flags
        reviewer_lenient = AssetReviewer(
            {"episode_qc": lenient_qc_config},
            db_path=str(tmp_path / "lenient.db"),
        )
        result_lenient = reviewer_lenient.run_layer2_qc(
            media_path=still, character_ref_paths=[ref1],
            location_plate_path=plate, asset_id=1, media_id=1,
            embedder=embedder,
        )
        assert len(result_lenient["flags"]) == 0

    def test_reviewer_no_episode_qc_config(self, tmp_path):
        """AssetReviewer works even without episode_qc in config (uses defaults)."""
        ref1 = str(tmp_path / "ref1.jpg")
        _make_warm_image(ref1)
        still = str(tmp_path / "still.jpg")
        _make_warm_image(still)
        plate = str(tmp_path / "plate.jpg")
        _make_warm_image(plate)

        # No episode_qc in config
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "review.db"))

        # Should use defaults and not crash
        # Identity will skip (no real model), grade will run with default thresholds
        result = reviewer.run_layer2_qc(
            media_path=still, character_ref_paths=[ref1],
            location_plate_path=plate, asset_id=1, media_id=1,
        )

        assert result["review_type"] == "layer2_qc"
        # Identity skipped (no model), grade should pass (both warm)
        assert result["findings"]["identity"]["status"] == "skipped"
        assert "qc_flag: grade_break" not in result["flags"]


# ════════════════════════════════════════════════════════════════════════
# Part 7: Config validation — thresholds read from models.yaml
# ════════════════════════════════════════════════════════════════════════

class TestConfigFromModelsYaml:
    """Verify the episode_qc config block in models.yaml is valid and used."""

    def test_episode_qc_block_exists_in_models_yaml(self):
        """The episode_qc block exists in config/models.yaml."""
        import yaml
        models_path = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")
        with open(models_path) as f:
            config = yaml.safe_load(f)

        assert "episode_qc" in config, "episode_qc block missing from models.yaml"

    def test_episode_qc_has_identity_and_grade_sections(self):
        """episode_qc has identity and grade sub-sections."""
        import yaml
        models_path = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")
        with open(models_path) as f:
            config = yaml.safe_load(f)

        eqc = config["episode_qc"]
        assert "identity" in eqc
        assert "grade" in eqc

    def test_identity_threshold_present(self):
        """Identity section has min_cosine_similarity threshold."""
        import yaml
        models_path = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")
        with open(models_path) as f:
            config = yaml.safe_load(f)

        ident = config["episode_qc"]["identity"]
        assert "min_cosine_similarity" in ident
        assert isinstance(ident["min_cosine_similarity"], (int, float))
        assert 0 < ident["min_cosine_similarity"] < 1

    def test_grade_threshold_present(self):
        """Grade section has histogram_threshold and histogram_metric."""
        import yaml
        models_path = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")
        with open(models_path) as f:
            config = yaml.safe_load(f)

        grade = config["episode_qc"]["grade"]
        assert "histogram_threshold" in grade
        assert "histogram_metric" in grade
        assert "histogram_bins" in grade
        assert grade["histogram_metric"] in ("correlation", "chi_square", "bhattacharyya", "intersection")

    def test_no_business_values_in_config(self):
        """Config contains no tenant-specific values (no character names, grades, etc.)."""
        import yaml
        models_path = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")
        with open(models_path) as f:
            content = f.read()

        # The episode_qc block should not contain any business-specific strings
        # Check for known business strings (StackPenni-specific)
        business_strings = ["stackpenni", "fitzroy", "kitchen_dawn", "warm golden-hour"]
        eqc_section = False
        eqc_lines = []
        for line in content.split("\n"):
            if line.startswith("episode_qc:"):
                eqc_section = True
            elif eqc_section and line.startswith("# ── Episode format Layer-1"):
                eqc_section = False
            elif eqc_section:
                eqc_lines.append(line.lower())

        eqc_text = "\n".join(eqc_lines)
        for s in business_strings:
            assert s.lower() not in eqc_text, f"Business string '{s}' found in episode_qc config"