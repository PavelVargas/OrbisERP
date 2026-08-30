from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
COMPACT_CSS = ROOT / "static/css/orbis_compact.css"


def test_compact_density_is_loaded_by_every_complete_html_document():
    missing = []
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        if "<body" in text.lower() and "orbis_compact.css" not in text:
            missing.append(str(path.relative_to(ROOT)))
    assert not missing, missing


def test_compact_density_defines_smaller_desktop_shell_and_controls():
    css = COMPACT_CSS.read_text(encoding="utf-8")
    assert "--ui-sidebar: 210px" in css
    assert "--ui-topbar: 50px" in css
    assert "--ui-control: 34px" in css
    assert "padding: 7px 9px !important" in css


def test_compact_density_keeps_tablet_mobile_touch_safe():
    css = COMPACT_CSS.read_text(encoding="utf-8")
    assert "@media (max-width: 900px)" in css
    # Desktop-only compression is intentionally isolated from touch layouts.
    assert "@media (min-width: 901px)" in css
