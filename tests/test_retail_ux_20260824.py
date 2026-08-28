from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def test_retail_is_split_into_task_subviews():
    route = read('routes/retail.py')
    nav = read('templates/retail/_nav.html')
    for path, endpoint in (
        ("/configuration", 'configuration'),
        ("/locations", 'locations'),
        ("/catalog-setup", 'catalog_setup'),
        ("/pricing", 'pricing'),
        ("/customer-programs", 'customer_programs'),
        ("/operations-center", 'operations_center'),
        ("/integrations", 'integrations'),
    ):
        assert path in route
        assert f"retail_bp.{endpoint}" in nav


def test_product_warranty_is_required_and_has_safe_default():
    model = read('models/products/products.py')
    retail_model = read('models/retail.py')
    create = read('templates/products/create.html')
    route = read('routes/products/products.py')
    migration = read('migrations/versions/e3f8b61c2a74_warranty_defaults.py')
    assert 'warranty_days = db.Column(db.Integer, nullable=False, default=30)' in model
    assert 'enable_warranties = db.Column(db.Boolean, nullable=False, default=True)' in retail_model
    assert 'name="warranty_days" required' in create
    assert "warranty_days < 1 or warranty_days > 3650" in route
    assert 'UPDATE products SET warranty_days = 30' in migration


def test_initial_stock_uses_selected_warehouse_and_has_a_kardex_entry():
    route = read('routes/products/products.py')
    create = read('templates/products/create.html')
    assert 'name="warehouse_id"' in create
    assert 'warehouse_id=selected_warehouse.id' in route
    assert "reason='Inventario inicial del producto'" in route


def test_quantities_are_human_readable_and_pos_respects_unit_weight_and_serial_policy():
    engine = read('services/sale_engine.py')
    sales = read('routes/sales/core.py')
    pos = read('templates/sales/create_sales.html')
    assert 'display_quantity' in engine
    assert 'product_quantity(' in sales
    assert 'product=product' in sales and 'uom=selected_uom' in sales
    assert "p.tracking!=='SERIAL'" in pos
    assert "p.sale_mode==='WEIGHT'" in pos
    assert "fractional?'0.001':'1'" in pos
    assert 'display_quantity(item.quantity)' in pos


def test_sale_detail_is_tabbed_and_warranty_first_class():
    detail = read('templates/sales/detail_sales.html')
    css = read('static/css/sales_css/detail_sales.css')
    assert 'Artículos y garantía' in detail
    assert 'data-sale-panel' in detail
    assert 'Abrir reclamación de garantía' in detail
    assert '.sale-view-tabs' in css
