from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def test_scanner_is_a_fixed_dark_workstation_with_orange_accent():
    template = read("templates/transfers/scanner_validation.html")
    css = read("static/css/scanner.css")

    assert '<html lang="es" class="scanner-dark">' in template
    assert '<body class="scanner-mode-page">' in template
    assert 'meta name="color-scheme" content="dark"' in template
    assert "This page intentionally remains dark" in css
    assert "--scan-bg: #0c0e11" in css
    assert "--scan-surface: #15191f" in css
    assert "--scan-accent: #f36b21" in css
    assert "body.scanner-mode-page > main#main-frame" in css
    assert "background: var(--scan-bg) !important" in css
    assert "padding: 30px clamp(18px, 3.2vw, 48px) 42px !important" in css
    assert '#manual-scan-form > button[type="submit"]' in css
    assert "background: var(--scan-accent) !important" in css
    assert "body.scanner-mode-page .status-badge.status-complete" in css
    assert "body.scanner-mode-page .sku-tag" in css
    assert "v='20260825-dark5'" in template
    assert "background: var(--scan-bg)" in css
    assert "--primary: #10b981" not in css


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
