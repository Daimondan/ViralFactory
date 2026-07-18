"""VF-VS-201 behavioral renderer-style configuration tests."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from assembly import AssemblyRenderer


def _write_style_module(modules_dir: Path, tenant: str, color: str, size: int) -> None:
    module_dir = modules_dir / tenant
    module_dir.mkdir(parents=True)
    (module_dir / "visual-style.md").write_text(
        "---\n"
        "render_styles:\n"
        "  overlay_styles:\n"
        "    hook:\n"
        f"      fontsize: {size}\n"
        f"      fontcolor: '{color}'\n"
        "      borderw: 2\n"
        "      bordercolor: black\n"
        "---\n"
        "# Visual Style\n\nTenant-owned presentation values.\n"
    )


def test_two_tenant_modules_resolve_different_overlay_styles_without_python_edits(tmp_path):
    config_dir = tmp_path / "config"
    modules_dir = tmp_path / "modules"
    config_dir.mkdir()
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
    )
    _write_style_module(modules_dir, "tenant-a", "#112233", 64)
    _write_style_module(modules_dir, "tenant-b", "#AABBCC", 76)

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

    assert tenant_a._resolve_overlay_style("hook")["fontcolor"] == "#112233"
    assert tenant_a._resolve_overlay_style("hook")["fontsize"] == 64
    assert tenant_b._resolve_overlay_style("hook")["fontcolor"] == "#AABBCC"
    assert tenant_b._resolve_overlay_style("hook")["fontsize"] == 76
    assert tenant_a._resolve_overlay_style("missing") == {
        "fontsize": 48,
        "fontcolor": "white",
        "borderw": 3,
        "bordercolor": "black",
    }
