from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_walk_in_sale_is_enabled_without_a_registered_client():
    core = source('routes/sales/core.py')
    actions = source('routes/sales/actions.py')
    template = source('templates/sales/create_sales.html')

    assert "'can_checkout': bool(items)" in core
    assert "'can_checkout': bool(items and sale.client_id)" not in core
    assert "if not sale.client_id:" not in actions
    assert "Consumidor final · cliente opcional" in template
    assert "'disabled' if not sale or not sale.items else ''" in template
    assert "if (finish) finish.disabled = !cart.has_items;" in template


def test_credit_and_loyalty_still_require_a_registered_client():
    actions = source('routes/sales/actions.py')
    retail = source('services/retail.py')
    template = source('templates/sales/create_sales.html')

    assert "if credit > 0:" in actions
    assert "ensure_credit_allowed(sale.client, credit)" in actions
    assert "Selecciona un cliente para vender a crédito." in retail
    assert "Selecciona un cliente para usar puntos de fidelidad." in retail
    assert "function checkoutNeedsClient(form)" in template
    assert "credit > 0 || points > 0" in template


def test_finish_sale_is_ajax_transactional_and_idempotent_for_the_operator():
    actions = source('routes/sales/actions.py')
    template = source('templates/sales/create_sales.html')

    assert "request.headers.get('X-Requested-With') == 'XMLHttpRequest'" in actions
    assert "Sale.query.filter_by(id=sale_id, company_id=company_id).with_for_update().first()" in actions
    assert "if sale.status == 'COMPLETED':" in actions
    assert "db.session.commit()" in actions
    assert "session.pop('current_sale_id', None)" in actions
    assert "async function submitSale(form)" in template
    assert "event.preventDefault();" in template
    assert "'Accept': 'application/json'" in template
    assert "'X-Requested-With': 'XMLHttpRequest'" in template
    assert "No se registró el pago ni se descontó inventario" in template


def test_post_commit_integration_failure_cannot_report_the_sale_as_failed():
    actions = source('routes/sales/actions.py')
    commit_pos = actions.index('db.session.commit()')
    event_pos = actions.index("emit_event(company_id, 'sale.completed'")
    success_pos = actions.index("return jsonify(ok=True", event_pos)

    assert commit_pos < event_pos < success_pos
    assert "Sale webhook scheduling failed after commit" in actions
    assert "except Exception:" in actions[event_pos - 100:event_pos + 900]


def test_authenticated_views_share_the_sidebar_visual_language():
    head = source('templates/layouts/app_head_assets.html')
    shell = source('templates/layouts/left_bar.html')
    css = source('static/css/app_final.css')

    assert "root.classList.add('theme-preload', 'orbis-authenticated')" in head
    assert "css/app_final.css" in shell
    assert "Authenticated visual system v7" in css
    assert "--orbis-graphite" in css
    assert "html.orbis-authenticated body:not(.pos-page) > main" in css
    assert ".workspace-header" in css and ".bo-header" in css and ".page-header" in css


def test_tablet_mode_is_a_universal_application_shell_not_a_single_page_skin():
    runtime = source('static/js/tablet_runtime.js')
    css = source('static/css/app_final.css')
    left = source('static/css/left.css')

    for marker in (
        'visualViewport', '--tablet-vh', '--tablet-vw', 'tablet-landscape',
        'tablet-portrait', 'tablet-keyboard-open', 'normalizeInteractiveTables',
        'orbis-tablet-table-wrap', 'scrollIntoView',
    ):
        assert marker in runtime

    assert "html.tablet-mode.orbis-authenticated body:not(.pos-page) > main" in css
    assert "grid-template-columns: minmax(0, 1fr) !important;" in css
    assert "min-height: 50px !important;" in css
    assert ".orbis-tablet-table-wrap" in css
    assert "html.tablet-mode .app-tablet-topbar" in left
    assert "html.tablet-mode .app-tablet-dock" in left


def test_unused_duplicate_templates_cannot_reintroduce_a_second_visual_system():
    duplicates = (
        'templates/cash/close.html',
        'templates/sales/pending.html',
        'templates/sales/quotes.html',
        'templates/sales/sales.html',
        'templates/workspace/activity.html',
        'templates/workspace/executive.html',
        'templates/warehouse/transfers_by_warehouse.html',
    )
    for relative in duplicates:
        assert not (ROOT / relative).exists(), relative


def test_pageshow_restores_checkout_state_from_the_live_cart_not_stale_server_markup():
    template = source('templates/sales/create_sales.html')

    assert "const hasItems = Boolean(posOrderItems?.querySelector('.order-item'));" in template
    assert "const hasClient = Boolean(posClientSelect?.value);" in template
    assert "button.id === 'pos-finish-sale' || button.id === 'pos-quote-sale'" in template
    assert "Boolean({{ (true if sale and sale.items else false)|tojson }})" not in template


def test_client_directory_compound_search_cannot_collapse_to_icon_width():
    css = source('static/css/app_final.css')

    assert ".clients-toolbar > label" in css
    assert "flex: 1 1 360px;" in css
    assert ".clients-toolbar > label > input" in css
    assert "min-width: 0 !important;" in css
    assert ".clients-toolbar > select" in css
    assert "width: min(230px, 100%) !important;" in css
