from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def test_scanner_is_an_adaptive_canonical_workstation():
    template = read("templates/transfers/scanner_validation.html")
    css = read("static/css/scanner.css")

    assert 'class="scanner-workspace ' in template
    assert '<body class="scanner-mode-page orbis-app">' in template
    assert 'meta name="color-scheme" content="light dark"' in template
    assert "same adaptive light/dark tokens" in css
    assert "--scan-bg: var(--ui-bg)" in css
    assert "--scan-surface: var(--ui-surface)" in css
    assert "--scan-accent: var(--ui-primary)" in css
    assert "--scan-text: var(--ui-text)" in css
    assert "body.scanner-mode-page > main#main-frame" in css
    assert "background: var(--scan-bg) !important" in css
    assert '#manual-scan-form > button[type="submit"]' in css
    assert "background: var(--scan-accent) !important" in css
    assert "body.scanner-mode-page .status-badge.status-complete" in css
    assert "body.scanner-mode-page .sku-tag" in css
    assert "v='20260829-polished2'" in template
    assert "rgba(" not in css
    assert "color-mix(" not in css


def test_scanner_uses_external_script_and_fractional_flow():
    template = read("templates/transfers/scanner_validation.html")
    script = read("static/js/scanner.js")

    assert "static', filename='js/scanner.js'" in template
    assert 'id="fractional-form"' in template
    assert 'step="0.001"' in template
    assert 'state.mode = "WAITING_QUANTITY"' in script
    assert "parseQuantity" in script
    assert "scan_codes" in script
    assert "AbortController" in script
    assert 'cache: "no-store"' in script


def test_scanner_api_supports_product_barcodes_and_tenant_destination_rules():
    routes = read("routes/transfer_routes/transfer_routes.py")

    assert "from models.retail import ProductBarcode" in routes
    assert "ProductBarcode.query.filter_by" in routes
    assert '"scan_codes": scan_codes' in routes
    assert '"expected_qty": display_quantity(transfer.quantity)' in routes
    assert "user.warehouse_id != transfer.to_warehouse_id" in routes
    assert "product.tracking in {'LOT', 'SERIAL'}" in routes
    assert "response.headers['Cache-Control'] = 'no-store, private'" in routes
    assert "request.referrer" not in routes


def test_transfer_and_scanner_menu_cannot_be_active_together():
    sidebar = read("templates/layouts/left_bar.html")

    assert "not request.path.startswith('/transfers/scanner')" in sidebar
    assert "request.path.startswith('/transfers/scanner-mode')" in sidebar


def test_scanner_permission_can_complete_the_scanner_workflow():
    permissions = read("permissions.py")
    assert "'transfer_bp.receive_transfer': ('transfers.receive', 'transfers.scanner')" in permissions


def test_accidental_scanner_block_is_not_duplicated_across_stylesheets():
    marker = "ORBIS_SCANNER_THEME_HARDENING_20260825"
    offenders = []
    for path in (ROOT / "static/css").rglob("*.css"):
        if marker in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
