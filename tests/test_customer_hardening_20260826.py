from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def source(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_receipt_printer_configuration_and_preview_are_exposed():
    config = source('templates/retail/configuration.html')
    receipt = source('templates/sales/receipt_thermal.html')
    nav = source('templates/layouts/left_bar.html')
    assert 'receiptDeviceConfig' in config
    assert 'default_receipt_width' in config and 'min="40"' in config and 'max="112"' in config
    assert 'receipt_printer_mode' in config and 'pairReceiptPrinter' in config
    assert 'receiptConfigPreview' in config
    assert 'ticketWidth' in receipt and 'Vista previa del ticket' in receipt
    assert 'Impresora y tickets' in nav


def test_cash_is_branch_scoped():
    route = source('routes/cash/cash.py')
    model = source('models/productivity.py')
    assert 'branch_id=branch.id' in route
    assert "Sale.branch_id == cash_session.branch_id" in route
    assert "Expense.branch_id == cash_session.branch_id" in route
    assert 'Las demás sucursales no se modifican' in route
    assert 'uq_cash_sessions_open_user_branch' in model


def test_purchase_inline_line_and_uom_guard():
    tpl = source('templates/purchase/purchase_detail.html')
    route = source('routes/purchase/purchase.py')
    assert 'purchase-inline-line' in tpl
    assert 'Producto *' in tpl and 'Cantidad *' in tpl and 'Costo *' in tpl and 'ITBIS *' in tpl
    assert 'allowed_uom_ids' in route
    assert 'no está habilitada para comprar este producto' in route


def test_returns_are_sale_first_and_inventory_linked():
    listing = source('templates/backoffice/returns.html')
    form = source('templates/backoffice/return_form.html')
    route = source('routes/backoffice.py')
    assert 'Busca por número de venta' in listing
    assert 'Disponible / vendible' in form and 'Cuarentena / revisión' in form and 'Dañado / no vendible' in form
    assert '_restore_available_stock' in route and '_add_condition_stock' in route
    assert "'SALE_RETURN'" in route


def test_warranty_stock_effect_is_explicit():
    tpl = source('templates/retail/warranties.html')
    route = source('routes/retail.py')
    assert 'Una garantía no devuelve automáticamente el producto al stock' in tpl
    assert "serial.status = 'WARRANTY'" in route
    assert "claim.serial.status = 'SCRAPPED'" in route
    assert "reason=f'Reemplazo garantía #{claim.id}'" in route


def test_user_edits_are_live_but_password_remains_security_boundary():
    users = source('routes/users/users.py')
    app = source('app.py')
    assert 'Ordinary edits are live' in users
    assert "session['branch_id'] = target_user.branch_id" in users
    assert "'user_role': authenticated_user.role" in app
    assert "target_user.set_password(password)" in users


def test_theme_prepaint_and_tablet_runtime_are_global():
    head = source('templates/layouts/app_head_assets.html')
    theme = source('static/js/theme-sync.js')
    tablet = source('static/js/tablet_runtime.js')
    assert 'theme-preload' in head and "localStorage.getItem('theme')" in head
    assert 'finishInitialPaint' in theme
    assert 'visualViewport' in tablet and 'tablet-keyboard-open' in tablet
    assert 'scrollIntoView' in tablet


def test_unit_imports_reject_fractional_stock_unless_configured():
    ops = source('routes/operations.py')
    quantity = source('services/quantity.py')
    assert "sale_mode == 'WEIGHT'" in ops
    assert "product_quantity(\n            row.get('stock')" in ops
    assert 'debe ser un número entero' in quantity


def test_feedback_is_visible_and_actionable():
    js = source('static/js/feedback.js')
    app = source('app.py')
    assert 'orbis-feedback-backdrop' in js
    assert 'Corrige la causa indicada y vuelve a intentar' in js
    assert 'Modo solo lectura: no se guardó ningún cambio' in app
