"""VF-VS-203 — Replace tautological config-style tests with behavioral ones.

This module is the explicit replacement for the deleted
``test_vf_au_302_304_config_style.py``. The old file verified acceptance
criteria by inspecting Python source (``inspect.getsource``) and DB schema
strings — not by exercising the config-driven resolution path.

The behavioral proof lives in:

* ``test_vf_vs_201_render_styles.py`` — overlay styles, two tenants, zero
  Python edits, different resolved parameters, safe fallback.
* ``test_vf_vs_202_sfx_presets.py`` — SFX presets, two tenants, zero Python
  edits, different resolved parameters, default-preset fallback.

This file pulls both concerns into one end-to-end pass so the replacement is
visible in a single place, and it pins the guardrail: the tautological file
must stay deleted.
"""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from assembly import AssemblyRenderer  # noqa: E402


def test_tautological_config_style_test_file_is_deleted():
    """The structural test file replaced by VF-VS-203 must not return."""
    removed = ROOT / "tests" / "test_vf_au_302_304_config_style.py"
    assert not removed.exists(), (
        f"{removed.name} was re-introduced. VF-VS-203 deleted it because its "
        "acceptance criteria were met with source-inspection, not behavior."
    )


def _write_config(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "render_styles.yaml").write_text(
        "version: 1\n"
        "overlay_styles:\n"
        "  default:\n"
        "    fontsize: 48\n"
        "    fontcolor: white\n"
        "    borderw: 3\n"
        "    bordercolor: black\n"
        "  hook:\n"
        "    fontsize: 60\n"
        "    fontcolor: white\n"
        "    borderw: 3\n"
        "    bordercolor: black\n"
        "sfx_default_preset: accent\n"
        "sfx_presets:\n"
        "  accent:\n"
        "    freq: '600'\n"
        "    duration: 0.2\n"
        "    volume: 0.3\n"
        "    type: sine\n"
    )


def _write_module(
    modules_dir: Path,
    tenant: str,
    hook_color: str,
    hook_size: int,
    accent_freq: str,
    accent_volume: float,
) -> None:
    module_dir = modules_dir / tenant
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "visual-style.md").write_text(
        "---\n"
        "render_styles:\n"
        "  overlay_styles:\n"
        "    hook:\n"
        f"      fontsize: {hook_size}\n"
        f"      fontcolor: '{hook_color}'\n"
        "      borderw: 2\n"
        "      bordercolor: black\n"
        "  sfx_presets:\n"
        "    accent:\n"
        f"      freq: '{accent_freq}'\n"
        "      duration: 0.2\n"
        f"      volume: {accent_volume}\n"
        "      type: sine\n"
        "---\n"
        "# Visual Style\n\nTenant-owned presentation values.\n"
    )


def _make_renderer(tmp_path: Path, config_dir: Path, modules_dir: Path, tenant: str):
    return AssemblyRenderer(
        {},
        db_path=str(tmp_path / f"{tenant}.db"),
        config_dir=str(config_dir),
        modules_dir=str(modules_dir),
        business_slug=tenant,
    )


def test_two_tenant_configs_render_different_overlay_and_sfx_parameters(tmp_path):
    """Two tenants, same Python, different resolved overlay + SFX parameters.

    This is the single behavioral proof that replaces the structural
    ``TestVisualStyleRenderTokens`` and ``TestConfigDrivenMusicSFX`` classes
    deleted from ``test_vf_au_302_304_config_style.py``.
    """
    config_dir = tmp_path / "config"
    modules_dir = tmp_path / "modules"
    _write_config(config_dir)
    _write_module(modules_dir, "tenant-a", "#112233", 64, "720", 0.25)
    _write_module(modules_dir, "tenant-b", "#AABBCC", 76, "980", 0.45)

    tenant_a = _make_renderer(tmp_path, config_dir, modules_dir, "tenant-a")
    tenant_b = _make_renderer(tmp_path, config_dir, modules_dir, "tenant-b")

    # Overlay styles — different per tenant, zero Python edits.
    assert tenant_a._resolve_overlay_style("hook")["fontcolor"] == "#112233"
    assert tenant_a._resolve_overlay_style("hook")["fontsize"] == 64
    assert tenant_b._resolve_overlay_style("hook")["fontcolor"] == "#AABBCC"
    assert tenant_b._resolve_overlay_style("hook")["fontsize"] == 76

    # SFX presets — different per tenant, zero Python edits.
    assert tenant_a._resolve_sfx_preset("accent")["freq"] == "720"
    assert tenant_a._resolve_sfx_preset("accent")["volume"] == 0.25
    assert tenant_b._resolve_sfx_preset("accent")["freq"] == "980"
    assert tenant_b._resolve_sfx_preset("accent")["volume"] == 0.45


def test_unknown_overlay_style_falls_back_to_default(tmp_path):
    """Missing style token resolves to the documented safe fallback.

    Replaces the structural ``test_overlay_styles_have_safe_fallback`` which
    only grepped source for the word 'default'.
    """
    config_dir = tmp_path / "config"
    modules_dir = tmp_path / "modules"
    _write_config(config_dir)
    _write_module(modules_dir, "tenant-a", "#112233", 64, "720", 0.25)

    renderer = _make_renderer(tmp_path, config_dir, modules_dir, "tenant-a")
    fallback = renderer._resolve_overlay_style("does-not-exist")
    assert fallback == {
        "fontsize": 48,
        "fontcolor": "white",
        "borderw": 3,
        "bordercolor": "black",
    }


def test_unknown_sfx_type_falls_back_to_default_preset(tmp_path):
    """Unknown SFX type resolves to the configured default preset.

    Replaces the structural fallback assertion in the deleted file.
    """
    config_dir = tmp_path / "config"
    modules_dir = tmp_path / "modules"
    _write_config(config_dir)
    _write_module(modules_dir, "tenant-a", "#112233", 64, "720", 0.25)

    renderer = _make_renderer(tmp_path, config_dir, modules_dir, "tenant-a")
    # Empty/unknown type → default preset ("accent") with tenant override.
    assert renderer._resolve_sfx_preset("")["freq"] == "720"
    assert renderer._resolve_sfx_preset("unknown-type")["freq"] == "720"


def test_silence_is_valid_when_sfx_absent(tmp_path):
    """Cue compiler must accept a beat with no SFX cues (SFX is optional).

    Behavioral replacement for ``TestConfigDrivenMusicSFX.silence_is_valid``.
    The full silent-piece regression also lives in
    ``test_vf_au_601_integration_suite.TestSilentPiece``.
    """
    from services.cue_compiler import CueCompiler

    beats = [{
        "beat_id": "b01",
        "vo_text": "test",
        "audio_intent": {"mode": "vo_only"},
    }]
    compiler = CueCompiler()
    timeline = compiler.compile(
        beats, [], vo_segments=[{"beat_id": "b01", "duration": 3.0, "text": "x"}]
    )
    assert len(timeline.sfx_events) == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))