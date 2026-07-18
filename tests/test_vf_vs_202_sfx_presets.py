"""VF-VS-202 behavioral SFX-preset configuration tests."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from assembly import AssemblyRenderer


def _write_sfx_module(modules_dir: Path, tenant: str, frequency: str, volume: float) -> None:
    module_dir = modules_dir / tenant
    module_dir.mkdir(parents=True)
    (module_dir / "visual-style.md").write_text(
        "---\n"
        "render_styles:\n"
        "  sfx_presets:\n"
        "    accent:\n"
        f"      freq: '{frequency}'\n"
        "      duration: 0.2\n"
        f"      volume: {volume}\n"
        "      type: sine\n"
        "---\n"
        "# Visual Style\n\nTenant-owned sound presentation values.\n"
    )


def test_two_tenant_modules_resolve_different_sfx_presets_without_python_edits(tmp_path):
    config_dir = tmp_path / "config"
    modules_dir = tmp_path / "modules"
    config_dir.mkdir()
    (config_dir / "render_styles.yaml").write_text(
        "version: 1\n"
        "overlay_styles:\n"
        "  default:\n"
        "    fontsize: 48\n"
        "    fontcolor: white\n"
        "sfx_default_preset: accent\n"
        "sfx_presets:\n"
        "  accent:\n"
        "    freq: '600'\n"
        "    duration: 0.2\n"
        "    volume: 0.3\n"
        "    type: sine\n"
    )
    _write_sfx_module(modules_dir, "tenant-a", "720", 0.25)
    _write_sfx_module(modules_dir, "tenant-b", "980", 0.45)

    tenant_a = AssemblyRenderer(
        {},
        db_path=str(tmp_path / "a.db"),
        config_dir=str(config_dir),
        modules_dir=str(modules_dir),
        business_slug="tenant-a",
    )
    tenant_b = AssemblyRenderer(
        {},
        db_path=str(tmp_path / "b.db"),
        config_dir=str(config_dir),
        modules_dir=str(modules_dir),
        business_slug="tenant-b",
    )

    assert tenant_a._resolve_sfx_preset("accent")["freq"] == "720"
    assert tenant_a._resolve_sfx_preset("accent")["volume"] == 0.25
    assert tenant_b._resolve_sfx_preset("accent")["freq"] == "980"
    assert tenant_b._resolve_sfx_preset("accent")["volume"] == 0.45
    assert tenant_a._resolve_sfx_preset("")["freq"] == "720"
