from pathlib import Path


def test_health_endpoint_does_not_require_database():
    from app import app
    app.config.update(TESTING=True)
    response = app.test_client().get('/operations/health/live')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'ok'


def test_commercial_endpoints_are_registered():
    from app import app
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert {
        'operations_bp.billing', 'operations_bp.billing_webhook',
        'operations_bp.onboarding', 'operations_bp.data_center',
        'operations_bp.export_data',
    } <= endpoints


def test_refreshed_operational_screens_are_registered():
    from app import app
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert {
        'company_bp.settings', 'launchpad_bp.launchpad', 'crm_bp.crm_index',
        'stock_bp.kardex_general', 'supplier_bp.supplier_list',
        'backoffice_bp.notifications', 'backoffice_bp.notification_open',
    } <= endpoints


def test_crm_state_layer_keeps_hidden_panels_hidden():
    css = Path('static/css/crm_css/crm_state.css').read_text(encoding='utf-8')
    template = Path('templates/crm/index.html').read_text(encoding='utf-8')

    assert '.crm-page [hidden]' in css
    assert 'display: none !important' in css
    assert 'id="errorState"' in template
    assert 'data-client-endpoint=' in template


def test_purchase_detail_uses_commercial_polish_layer():
    template = Path('templates/purchase/purchase_detail.html').read_text(encoding='utf-8')
    css = Path('static/css/order_css/purchase_detail_polish.css').read_text(encoding='utf-8')

    assert 'purchase_detail_polish.css' in template
    assert "v='11'" in template
    head = template.split('</head>', 1)[0]
    assert 'purchase_detail_polish.css' in head
    assert 'display: grid' in css
    assert '.progress-step {' in css
    assert 'class="order-progress"' in template
    assert 'class="line-builder"' in template
    assert 'class="configuration-column"' in template
    assert '.summary-card' in css


def test_purchase_list_has_compact_filters_and_operational_summary():
    template = Path('templates/purchase/purchase_list.html').read_text(encoding='utf-8')
    css = Path('static/css/order_css/purchase_list.css').read_text(encoding='utf-8')

    assert 'class="purchase-metrics"' in template
    assert 'class="filters-popover"' in template
    assert 'name="supplier_id"' in template
    assert '.purchases-table-wrap' in css
