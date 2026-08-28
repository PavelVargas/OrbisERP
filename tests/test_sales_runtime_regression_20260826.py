from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative_path):
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_new_pos_line_keeps_relationships_available_before_flush():
    route = source('routes/sales/core.py')
    constructor = route.split('item = SaleItem(', 1)[1].split(')', 1)[0]
    assert 'sale=sale' in constructor
    assert 'product=product' in constructor
    assert 'warehouse=warehouse' in constructor
    assert 'variant=variant' in constructor
    assert constructor.index('product=product') < route.split('item = SaleItem(', 1)[1].index('_set_line_price(item, sale)')


def test_sale_price_rejects_missing_or_cross_tenant_product_safely():
    retail = source('services/retail.py')
    assert 'if product is None:' in retail
    assert 'El producto no pertenece a la empresa usada para calcular el precio' in retail
    assert 'La variante no es válida para calcular el precio de este producto' in retail


def test_pos_add_uses_json_feedback_instead_of_a_500_page():
    route = source('routes/sales/core.py')
    template = source('templates/sales/create_sales.html')
    app = source('app.py')
    assert "request.headers.get('X-Requested-With') == 'XMLHttpRequest'" in route
    assert 'except (BusinessRuleError, NumericValueError) as exc:' in route
    assert 'return jsonify(' in route and 'cart = _sale_cart_payload(sale)' in route and 'cart=cart' in route
    assert "'X-Requested-With': 'XMLHttpRequest'" in template
    assert 'window.OrbisFeedback?.show' in template
    assert 'renderCart(payload.cart)' in template
    assert 'Unexpected POS add failure' in route
    assert 'No se guardó ningún cambio' in route
    assert "window.location.assign(payload.redirect || window.location.href)" in template
    assert 'alert(' not in template
    assert '@app.errorhandler(NumericValueError)' in app
    assert 'def _expects_json_response()' in app


def test_pos_cards_have_visible_touch_action_and_not_only_an_icon():
    template = source('templates/sales/create_sales.html')
    css = source('static/css/sales_css/create_sales.css')
    assert 'class="add-product-glyph"' in template
    assert 'class="add-product-label">Agregar</span>' in template
    assert '.pos-page #product-grid .add-product-btn {' in css
    assert 'grid-column: 1 / -1;' in css
    assert 'min-height: 46px !important;' in css
    assert 'sale-product-category-mark' in template
    assert 'cart-empty-icon' in template


def test_sidebar_sections_are_collapsible_and_persisted():
    shell = source('templates/layouts/left_bar.html')
    js = source('static/js/left.js')
    css = source('static/css/left.css')
    assert 'data-nav-section="sales"' in shell
    assert 'class="section-title nav-section-toggle' in shell
    assert "const navSectionKey = 'orbis-nav-sections-v3';" in js
    assert "filter(section => !section.querySelector('.nav-item.active'))" in js
    assert "section.classList.toggle('is-collapsed'" in js
    assert '.nav-section.is-collapsed .nav-items' in css
    assert 'OrbisLocalIcons' in js
    assert 'orbis-nav-icon' in js
    assert '.nav-icon > .orbis-nav-icon' in css
    assert 'safeInternalUrl' in js
    assert 'results.replaceChildren' in js


def test_pos_cart_mutations_update_without_a_full_page_reload():
    route = source('routes/sales/core.py')
    template = source('templates/sales/create_sales.html')
    css = source('static/css/sales_css/create_sales.css')
    assert 'def _sale_cart_payload(sale):' in route
    assert "message='Producto eliminado del pedido.'" in route
    assert 'sale.items.remove(item)' in route
    assert 'function renderCart(cart)' in template
    assert 'async function removeCartItem(form)' in template
    assert "posOrderItems?.addEventListener('submit'" in template
    assert 'if (!payload.cart)' in template
    assert '.pos-cart-open .pos-right' in css
    assert 'grid-template-columns: minmax(0, 1fr) !important;' in css


def test_application_logging_does_not_duplicate_flask_records():
    app = source('app.py')
    reports = source('routes/reports/reports.py')
    assert 'if default_handler in app.logger.handlers:' in app
    assert 'app.logger.removeHandler(default_handler)' in app
    assert 'app.logger.propagate = False' in app
    assert 'logging.basicConfig' not in reports


def test_remaining_business_validation_uses_orbis_feedback_not_native_alerts():
    company = source('templates/company/settings.html')
    transfer = source('templates/transfers/create.html')
    assert 'alert(' not in company
    assert 'alert(' not in transfer
    assert 'window.OrbisFeedback?.show' in company
    assert 'window.OrbisFeedback?.show' in transfer
    assert '<script nonce="{{ g.csp_nonce }}">' in company


def test_pos_urls_and_final_actions_are_not_brittle_or_premature():
    template = source('templates/sales/create_sales.html')
    css = source('static/css/sales_css/create_sales.css')
    assert 'function productAddUrl(productId)' in template
    assert "const addProductUrlSentinel = '2147483647';" in template
    assert 'replace(/0$/' not in template
    assert 'function bindProgressSubmit(form, title, detail)' in template
    assert '¡Venta Registrada!' not in template
    assert '¡Cotización Guardada!' not in template
    assert 'async function submitSale(form)' in template
    assert "finishSaleForm?.addEventListener('submit'" in template
    assert "'Venta registrada'" in template
    assert "window.setTimeout(() => window.location.assign(payload.redirect), 280)" in template
    assert '.processing-ring' in css
    assert 'role="group"' in template
    assert 'role="button" tabindex=' not in template


def test_pos_cards_do_not_turn_the_whole_card_into_a_hidden_add_button():
    template = source('templates/sales/create_sales.html')
    assert "card.addEventListener('click'" not in template


def test_pos_client_price_list_and_promotion_relationships_are_current_in_request():
    route = source('routes/sales/core.py')
    promotions = source('routes/sales/quotes.py')
    template = source('templates/sales/create_sales.html')

    assert 'sale.client = client' in route
    assert 'sale.price_list = selected' in route
    assert 'sale.price_list = price_list' in route
    assert 'Unexpected POS client assignment failure' in route
    assert 'sale.promotion = None' in route

    assert 'sale.promotion = promotion' in promotions
    assert 'sale.promotion = None' in promotions
    assert 'async function assignSaleClient(form)' in template
    assert "posClientSelect.addEventListener('change'" in template
    assert 'await fetchProducts(barcodeInput.value.trim())' in template


def test_tablet_order_line_reserves_space_for_the_touch_remove_button():
    css = source('static/css/sales_css/create_sales.css')
    assert 'grid-template-columns: 30px minmax(0, 1fr) auto 38px;' in css
    assert 'grid-template-columns: 30px minmax(0, 1fr) auto 44px;' in css


def test_pos_card_cursor_does_not_promise_a_hidden_card_click_action():
    css = source('static/css/sales_css/create_sales.css')
    final_card_rule = css.rsplit('.pos-page #product-grid > article.retail-pos-card {', 1)[1].split('}', 1)[0]
    assert 'cursor: default;' in final_card_rule
