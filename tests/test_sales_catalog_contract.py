from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_sales_catalog_image_fallback_does_not_dereference_missing_variant():
    source = read('routes/sales/core.py')
    assert 'image_url = product_image_url(product)' in source
    assert "url_for('static', filename=image_path) if image_path else None" in source
    assert 'filename=(variant.image_path or product.image_path)' not in source
    assert 'filename=(variant.image_path or p.image_path)' not in source


def test_pos_catalog_reports_http_errors_and_uses_named_endpoints():
    template = read('templates/sales/create_sales.html')
    assert "url_for('sales_bp.get_products')|tojson" in template
    assert "url_for('sales_bp.add_to_cart', product_id=2147483647)|tojson" in template
    assert "const addProductUrlSentinel = '2147483647';" in template
    assert "product_id=0" not in template
    assert 'if (!response.ok)' in template
    assert 'Array.isArray(products)' in template
    assert 'catalog-retry' in template
    assert 'catalog-status' in template
    assert "error?.name === 'AbortError'" in template


def test_pos_renderer_keeps_product_in_scope_for_uom_controls():
    """Regression for the catalog-wide ReferenceError seen in the POS.

    The former renderer referenced ``p.uoms`` in a second card loop even though
    ``p`` existed only inside ``products.map``. That made a valid JSON response
    look like an endpoint failure and replaced every product with the error UI.
    """
    template = read('templates/sales/create_sales.html')
    marker = "productGrid.querySelectorAll('.retail-pos-card').forEach(card => {"
    card_loop = template.split(marker, 1)[1].split("productGrid.querySelectorAll('.add-product-btn')", 1)[0]
    assert 'const idx = Number(card.dataset.index);' in card_loop
    assert 'const p = products[idx];' in card_loop
    assert 'if (!p) return;' in card_loop
    assert card_loop.index('const p = products[idx];') < card_loop.index('(p.uoms || [])')


def test_pos_coupon_and_icon_spacing_override_global_form_rules():
    template = read('templates/sales/create_sales.html')
    css = read('static/css/sales_css/create_sales.css')

    assert 'class="promotion-form"' in template
    assert 'class="promotion-code-input"' in template
    assert 'class="promotion-apply-btn"' in template
    assert '<body class="pos-page">' in template

    assert '.pos-page #barcode-input {' in css
    assert 'padding: 0 42px 0 46px !important;' in css
    assert '.pos-page .client-select {' in css
    assert 'padding: 0 38px 0 42px !important;' in css
    assert '.pos-page .promotion-form {' in css
    assert 'grid-template-columns: minmax(0, 1fr) auto;' in css
    assert '.pos-page .promotion-apply-btn {' in css
    assert 'width: auto !important;' in css


def test_pos_catalog_is_resilient_to_one_invalid_product_configuration():
    route = read('routes/sales/core.py')
    assert "search_query = request.args.get('search', '').strip()[:120]" in route
    assert 'POS catalog skipped invalid UOM configuration' in route
    assert 'POS catalog found invalid pricing' in route
    assert "'available': not row_errors" in route
    assert "'unavailable_reason': ' '.join(row_errors)" in route
    assert "response.headers['Cache-Control'] = 'private, no-store, max-age=0'" in route


def test_pos_uses_safe_area_viewport():
    template = read('templates/sales/create_sales.html')
    assert 'viewport-fit=cover' in template
