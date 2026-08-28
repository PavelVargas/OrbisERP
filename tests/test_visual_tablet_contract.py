from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_chrome_loads_visual_coherence_and_tablet_runtime():
    shell = (ROOT / 'templates/layouts/left_bar.html').read_text(encoding='utf-8')
    head = (ROOT / 'templates/layouts/app_head_assets.html').read_text(encoding='utf-8')
    assert "css/ui_unification.css" in shell
    assert 'app-tablet-topbar' in shell
    assert 'app-tablet-dock' in shell
    assert 'global-search-modal' in shell
    assert 'tablet-search-trigger' in shell
    assert "js/tablet_runtime.js" in head


def test_launchpad_is_a_real_tablet_document():
    template = (ROOT / 'templates/launchpad/index.html').read_text(encoding='utf-8')
    assert '<html lang="es" class="tablet-mode">' in template
    assert 'viewport-fit=cover' in template
    assert "css/ui_unification.css" in template
    assert "js/tablet_runtime.js" in template
    assert 'tablet-shell' in template
    assert 'tablet-launch-dock' in template
    assert 'data-launch-section="sales"' in template
    assert 'data-section="{{ module.section }}"' in template


def test_tablet_runtime_tracks_visual_viewport_and_keyboard():
    source = (ROOT / 'static/js/tablet_runtime.js').read_text(encoding='utf-8')
    assert 'visualViewport' in source
    assert '--tablet-vh' in source
    assert 'tablet-keyboard-open' in source
    assert "scrollIntoView" in source


def test_workspace_base_supports_device_safe_areas():
    source = (ROOT / 'templates/workspace/base.html').read_text(encoding='utf-8')
    assert 'viewport-fit=cover' in source
    assert 'workspace-page orbis-page' in source


def test_desktop_sidebar_collapse_is_disabled_inside_tablet_mode():
    source = (ROOT / 'static/js/left.js').read_text(encoding='utf-8')
    assert "!document.documentElement.classList.contains('tablet-mode')" in source


def test_tablet_layout_uses_runtime_viewport_height():
    left = (ROOT / 'static/css/left.css').read_text(encoding='utf-8')
    launchpad = (ROOT / 'static/css/launchpad.css').read_text(encoding='utf-8')
    assert 'var(--tablet-vh,100dvh)' in left
    assert 'var(--tablet-vh,100dvh)' in launchpad
