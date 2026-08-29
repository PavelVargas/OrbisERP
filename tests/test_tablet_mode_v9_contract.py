from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_tablet_mode_persists_across_module_navigation_until_explicit_exit():
    app = read('app.py')
    dashboard = read('routes/dashboard/dashboard.py')
    launchpad = read('routes/launchpad/launchpad.py')
    head = read('templates/layouts/app_head_assets.html')
    runtime = read('static/js/tablet_runtime.js')

    assert 'sync_tablet_mode_preference' in app
    assert "request.cookies.get(TABLET_UI_COOKIE)" in app
    assert "session['tablet_mode'] = True" in app
    assert "TABLET_MODE_COOKIE = 'orbis_ui_mode'" in dashboard
    assert "return _tablet_preference_response(response, True)" in dashboard
    assert "return _tablet_preference_response(response, False)" in dashboard
    assert "'orbis_ui_mode', 'desktop'" in launchpad
    assert "localStorage.getItem('orbis-tablet-mode') === '1'" in head
    assert "writeTabletPreference(true)" in runtime
    assert "writeTabletPreference(false)" in runtime


def test_tablet_shell_is_available_for_client_continuity_but_hidden_on_desktop():
    shell = read('templates/layouts/left_bar.html')
    css = read('static/css/tablet_experience.css')

    assert '{% if session.get(\'tablet_mode\') %}\n<header class="app-tablet-topbar"' not in shell
    assert 'html:not(.tablet-mode)' in css
    assert '.app-tablet-topbar' in css
    assert '.tablet-section-sheet' in css
    assert 'display: none !important' in css


def test_light_theme_dock_and_sheet_use_theme_tokens_not_permanent_dark_surfaces():
    css = read('static/css/tablet_experience.css')

    assert '--tablet-nav-surface: var(--ui-surface-soft)' in css
    assert 'color-mix' not in css
    assert '--tablet-nav-strong: var(--ui-text)' in css
    assert 'background: var(--tablet-nav-surface) !important' in css
    assert 'background: var(--tablet-nav-surface-solid) !important' in css
    assert 'color: var(--tablet-nav-strong) !important' in css
    assert 'html.dark.tablet-mode' in css


def test_dock_is_compact_and_content_finishes_above_it():
    css = read('static/css/tablet_experience.css')

    assert '--tablet-dock-height: 58px' in css
    assert '--tablet-dock-safe: 78px' in css
    assert 'min-height: var(--tablet-dock-height) !important' in css
    assert 'padding-bottom: max(var(--tablet-dock-safe)' in css
    assert 'width: min(680px, calc(100% - 24px)) !important' in css


def test_tablet_navigation_has_motion_with_reduced_motion_escape_hatch():
    css = read('static/css/tablet_experience.css')
    runtime = read('static/js/tablet_runtime.js')

    assert '@keyframes orbisTabletPageIn' in css
    assert '@keyframes orbisTabletDockIn' in css
    assert '@keyframes orbisTabletCardIn' in css
    assert 'tablet-navigating' in css
    assert '@media (prefers-reduced-motion: reduce)' in css
    assert 'initNavigationMotion' in runtime
    assert "root.classList.add('tablet-navigating')" in runtime
    assert 'location.assign(target.href)' in runtime


def test_final_tablet_experience_layer_loads_after_generated_responsive_rules():
    shell = read('templates/layouts/left_bar.html')
    launchpad = read('templates/launchpad/index.html')

    assert shell.index('css/tablet_responsive.css') < shell.index('css/tablet_experience.css')
    assert launchpad.index('css/tablet_responsive.css') < launchpad.index('css/tablet_experience.css')
    assert '20260827-tablet10' in shell
    assert '20260827-tablet10' in launchpad
