from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def test_active_tablet_session_cannot_be_cleared_by_legacy_desktop_cookie():
    app = read('app.py')
    assert "if session.get('tablet_mode') or _request_has_tablet_signal():" in app
    assert "elif preference == '0'" not in app
    assert "LEGACY_TABLET_COOKIE = 'orbis_tablet_mode'" in app
    assert "TABLET_UI_COOKIE = 'orbis_ui_mode'" in app
    assert "request.cookies.getlist(LEGACY_TABLET_COOKIE)" in app


def test_every_url_for_navigation_inherits_tablet_context():
    app = read('app.py')
    runtime = read('static/js/tablet_runtime.js')
    assert 'def propagate_tablet_mode(endpoint, values):' in app
    assert "values.setdefault(TABLET_UI_QUERY, '1')" in app
    assert "target.searchParams.set(TABLET_QUERY_PARAM, '1')" in runtime
    assert 'stampTabletForms' in runtime


def test_launchpad_cards_explicitly_enter_modules_as_tablet_requests():
    launchpad = read('routes/launchpad/launchpad.py')
    needle = '"route": ' + 'url_' + 'for(' ; card_lines = [line for line in launchpad.splitlines() if needle in line]
    assert len(card_lines) >= 17
    assert all('_tablet=1' in line for line in card_lines)


def test_authenticated_templates_server_render_tablet_class_before_javascript():
    templates = []
    for path in (ROOT / 'templates').rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        if "layouts/app_head_assets.html" in text:
            templates.append((path, text))
    assert templates
    missing = [str(path.relative_to(ROOT)) for path, text in templates
               if 'tablet_mode_active' not in text.split('<head', 1)[0]]
    assert not missing, f'Authenticated templates without server tablet class: {missing}'


def test_canonical_cookie_has_precedence_over_legacy_cookie_in_client_bootstrap():
    head = read('templates/layouts/app_head_assets.html')
    shell = read('templates/layouts/left_bar.html')
    runtime = read('static/js/tablet_runtime.js')
    for text in (head, shell):
        assert 'orbis_ui_mode=(tablet|desktop)' in text
        assert 'canonicalUiMode !== \'desktop\'' in text
        assert "orbis_tablet_mode=1" in text
        assert "tabletCookie === '0'" not in text
    assert "TABLET_PREFERENCE_COOKIE = 'orbis_ui_mode'" in runtime
    assert "LEGACY_TABLET_PREFERENCE_COOKIE = 'orbis_tablet_mode'" in runtime
