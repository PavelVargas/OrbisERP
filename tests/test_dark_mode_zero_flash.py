from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def test_prepaint_seeds_browser_canvas_before_external_css():
    for relative in ('templates/layouts/theme_prepaint.html', 'templates/layouts/app_head_assets.html'):
        source = read(relative)
        assert 'meta name="color-scheme"' in source
        assert 'data-orbis-theme-color' in source
        assert '#191b1f' in source
        assert 'html.orbis-route-leaving body::after' not in source


def test_theme_runtime_does_not_block_full_document_navigation():
    source = read('static/js/theme-sync.js')
    assert 'function beginRouteLeave()' not in source
    assert "classList.add('orbis-route-leaving')" not in source
    assert 'setTimeout' not in source
    assert 'applyTheme(preferredTheme(), false)' in source


def test_page_entry_motion_never_fades_entire_view_from_transparent():
    commercial = read('static/css/commercial.css')
    assert '@keyframes orbisPageIn { from { transform:' in commercial
    assert '@keyframes orbisPageIn { from { opacity:' not in commercial
    tablet = read('static/css/tablet_experience.css')
    page_block = tablet.split('@keyframes orbisTabletPageIn', 1)[1].split('}', 2)[0]
    assert 'opacity:' not in page_block
