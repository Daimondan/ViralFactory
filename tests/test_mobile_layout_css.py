from pathlib import Path


CSS_PATH = Path(__file__).parents[1] / "src" / "static" / "vf.css"


def test_topbar_wraps_without_horizontal_overflow_on_mobile():
    css = CSS_PATH.read_text(encoding="utf-8")

    mobile_start = css.index("@media (max-width: 768px) {")
    mobile_end = css.index("}\n\n/* ── Top Bar", mobile_start) + 1
    mobile_rules = css[mobile_start:mobile_end]

    assert ".topbar { flex-wrap: wrap;" in mobile_rules
    assert ".topbar nav { flex: 1 1 100%; min-width: 0; flex-wrap: wrap;" in mobile_rules
