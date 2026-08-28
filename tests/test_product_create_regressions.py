from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_create_product_does_not_use_product_before_construction():
    source = (ROOT / 'routes/products/products.py').read_text(encoding='utf-8')
    start = source.index("def create_product():")
    constructed = source.index("        product = Product(", start)
    before = source[start:constructed]
    assert 'product.id' not in before


def test_product_photos_are_manual_only():
    create_html = (ROOT / 'templates/products/create.html').read_text(encoding='utf-8')
    edit_html = (ROOT / 'templates/products/edit.html').read_text(encoding='utf-8')
    operations = (ROOT / 'routes/operations.py').read_text(encoding='utf-8')
    resolver = (ROOT / 'services/product_images.py').read_text(encoding='utf-8')
    assert 'name="image_url"' not in create_html
    assert 'name="image_url"' not in edit_html
    assert "'image_url', 'image_file'" not in operations
    assert "getattr(product, 'image_url'" not in resolver


def test_product_form_lengths_match_database_contract():
    create_html = (ROOT / 'templates/products/create.html').read_text(encoding='utf-8')
    source = (ROOT / 'routes/products/products.py').read_text(encoding='utf-8')
    assert 'name="name" required maxlength="150"' in create_html
    assert 'name="sku" required maxlength="50"' in create_html
    assert 'len(name) > 150 or len(sku) > 50' in source


def test_initial_stock_is_auditable_and_tracked_stock_starts_at_zero():
    source = (ROOT / 'routes/products/products.py').read_text(encoding='utf-8')
    assert "tracking in {'LOT', 'SERIAL'}" in source
    assert "reason='Inventario inicial del producto'" in source
    operations = (ROOT / 'routes/operations.py').read_text(encoding='utf-8')
    assert "reason='Inventario inicial por importación'" in operations
