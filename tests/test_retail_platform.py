from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_retail_2_migration_is_configured_head_and_completes_returns():
    migration = (ROOT / 'migrations/versions/8d6c1a42f950_retail_returns_warranty.py').read_text(encoding='utf-8')
    assert "revision = '8d6c1a42f950'" in migration
    assert "down_revision = '7a9c4e21b6d0'" in migration
    for token in ('sale_return_item_lot_allocations', 'sale_return_item_serials', 'inventory_condition_stock', 'inventory_serial_events'):
        assert token in migration


def test_returns_preserve_traceability_and_physical_disposition():
    route = (ROOT / 'routes/backoffice.py').read_text(encoding='utf-8')
    template = (ROOT / 'templates/backoffice/return_form.html').read_text(encoding='utf-8')
    assert '_restore_lot_trace' in route
    assert '_restore_serial_trace' in route
    assert "{'AVAILABLE', 'QUARANTINE', 'DAMAGED', 'NONE'}" in route
    assert 'disposition_' in template
    assert 'serial_' in template


def test_loyalty_can_be_redeemed_as_a_transactional_sale_payment():
    service = (ROOT / 'services/retail.py').read_text(encoding='utf-8')
    actions = (ROOT / 'routes/sales/actions.py').read_text(encoding='utf-8')
    model = (ROOT / 'models/retail.py').read_text(encoding='utf-8')
    assert 'def redeem_loyalty' in service
    assert "event_type='REDEEM'" in service
    assert 'loyalty_points' in actions
    assert "'LOYALTY'" in model


def test_warranty_has_single_operational_center_and_serial_history():
    route = (ROOT / 'routes/retail.py').read_text(encoding='utf-8')
    permissions = (ROOT / 'permissions.py').read_text(encoding='utf-8')
    assert "@retail_bp.get('/warranties')" in route
    assert 'InventorySerialEvent' in route
    assert "'retail_bp.warranties': ('sales.warranties',)" in permissions
    assert (ROOT / 'templates/retail/warranties.html').is_file()


def test_retail_reporting_uses_true_last_sale_for_slow_movers():
    source = (ROOT / 'routes/reports/reports.py').read_text(encoding='utf-8')
    assert "func.max(Sale.created_at).label('last_sale')" in source
    assert "group_by(SaleItem.product_id)" in source
    assert "'/reports/retail-performance'" not in source  # route uses blueprint-local path only


def test_quantity_domain_keeps_fractional_stock_outside_serial_only_boundaries():
    inventory = (ROOT / 'routes/operations.py').read_text(encoding='utf-8')
    quantity = (ROOT / 'services/quantity.py').read_text(encoding='utf-8')
    sales_service = (ROOT / 'services/retail.py').read_text(encoding='utf-8')
    assert 'product_quantity(' in inventory
    assert 'product=product' in inventory and 'uom=product.base_uom' in inventory
    assert 'tracking in {"SERIAL", "SERIALIZED"}' in quantity
    assert '"WEIGHT", "FRACTIONAL", "DECIMAL", "VARIABLE_WEIGHT"' in quantity
    # Serial counts remain intentionally restricted to whole units.
    assert "productos serializados solo admiten cantidades enteras" in sales_service.lower()


def test_http_release_smokes_new_retail_operational_views():
    source = (ROOT / 'tests/test_http_release.py').read_text(encoding='utf-8')
    assert "'/retail/warranties'" in source
    assert "'/retail/quality'" in source
    assert "'/reports/retail-performance'" in source


def test_product_specific_uom_and_warranty_replacement_migration():
    migration = (ROOT / 'migrations/versions/9f4a2c7e1b33_product_uom_and_warranty_replacement.py').read_text(encoding='utf-8')
    models = (ROOT / 'models/retail.py').read_text(encoding='utf-8')
    service = (ROOT / 'services/retail.py').read_text(encoding='utf-8')
    assert "revision = '9f4a2c7e1b33'" in migration
    assert "down_revision = '8d6c1a42f950'" in migration
    assert 'product_uom_conversions' in migration
    assert 'replacement_serial_id' in migration
    assert 'class ProductUomConversion' in models
    assert 'uom_factor_to_base' in service


def test_packaging_uom_requires_product_specific_factor_and_quality_is_operational():
    products = (ROOT / 'routes/products/products.py').read_text(encoding='utf-8')
    retail_service = (ROOT / 'services/retail.py').read_text(encoding='utf-8')
    retail_route = (ROOT / 'routes/retail.py').read_text(encoding='utf-8')
    assert 'def _ensure_default_uom_factor' in products
    assert '1 caja = 24 unidades' in products
    assert 'Ambiguous packaging' in retail_service
    assert "@retail_bp.get('/quality')" in retail_route
    assert "@retail_bp.post('/quality/lots/<int:row_id>/<action>')" in retail_route
    assert "@retail_bp.post('/quality/serials/<int:row_id>/<action>')" in retail_route


def test_static_release_gate_and_retail_docs_are_shipped():
    gate = (ROOT / 'scripts/static_release_audit.py').read_text(encoding='utf-8')
    cert = (ROOT / 'scripts/certify_release.sh').read_text(encoding='utf-8')
    docs = (ROOT / 'RETAIL_PLATFORM.md').read_text(encoding='utf-8')
    assert 'check_jinja' in gate and 'check_migrations' in gate and 'check_assets_and_endpoints' in gate
    assert 'TEST_DATABASE_URL' in cert
    assert 'export DATABASE_URL="$TEST_DATABASE_URL"' in cert
    assert 'Variantes' in docs and 'FEFO' in docs and 'terminales POS' in docs


def test_retail_uom_seed_uses_postgresql_numeric_bind_types():
    migration = (ROOT / 'migrations/versions/7a9c4e21b6d0_retail_platform.py').read_text(encoding='utf-8')
    assert "from decimal import Decimal" in migration
    assert "CAST(:factor AS NUMERIC(18, 6))" in migration
    assert "CAST(:rounding AS NUMERIC(12, 6))" in migration
    assert "sa.bindparam('factor', type_=FACTOR)" in migration
    assert "sa.bindparam('rounding', type_=sa.Numeric(12, 6))" in migration
    assert "Decimal('0.001')" in migration
    assert '.bindparams(name=name, symbol=symbol, category=category, factor=factor' not in migration


def test_retail_bootstrap_migration_repairs_precreated_orm_tables():
    migration = (ROOT / 'migrations/versions/7a9c4e21b6d0_retail_platform.py').read_text(encoding='utf-8')
    assert 'Repair SQL-level defaults' in migration
    assert 'INSERT INTO company_retail_settings (' in migration
    for token in (
        'industry_profile', 'enable_variants', 'enable_uom', 'enable_price_lists',
        'costing_method', 'default_receipt_width', 'updated_at', 'CURRENT_TIMESTAMP'
    ):
        assert token in migration
    assert 'INSERT INTO branches (company_id, code, name, status, is_main, created_at)' in migration
    assert 'INSERT INTO price_lists (company_id, code, name, currency_code, is_default, active, created_at)' in migration
    assert 'allow_fraction, active, created_at' in migration


def test_release_closes_startup_and_rbac_consistency_gaps():
    app_source = (ROOT / 'app.py').read_text(encoding='utf-8')
    permissions = (ROOT / 'permissions.py').read_text(encoding='utf-8')
    hardening = (ROOT / 'tests/test_production_hardening.py').read_text(encoding='utf-8')

    assert "'sales_bp.thermal_receipt': ('sales.print',)" in permissions
    assert "endpoint.startswith(('static', 'superadmin_bp.', 'api_v1.'))" in hardening
    assert "assert 'qty = product_quantity(' in core" in hardening
    assert "with app.app_context():\n            try:\n                require_current_schema()" in app_source
    assert 'db.session.rollback()\n                raise' in app_source
