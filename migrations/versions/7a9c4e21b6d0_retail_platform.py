"""retail platform: branches, variants, pricing, tracking and POS

Revision ID: 7a9c4e21b6d0
Revises: 6f7b2d4c9a11
"""
from alembic import op
from decimal import Decimal
import sqlalchemy as sa

revision = '7a9c4e21b6d0'
down_revision = '6f7b2d4c9a11'
branch_labels = None
depends_on = None

QTY = sa.Numeric(14, 3)
FACTOR = sa.Numeric(18, 6)
MONEY = sa.Numeric(12, 2)


def _cols(inspector, table):
    try:
        return {c['name'] for c in inspector.get_columns(table)}
    except Exception:
        return set()


def _checks(inspector, table):
    try:
        return {row.get('name') for row in inspector.get_check_constraints(table)}
    except Exception:
        return set()


def _indexes(inspector, table):
    try:
        return {row.get('name') for row in inspector.get_indexes(table)}
    except Exception:
        return set()


def _column(inspector, table, name):
    for row in inspector.get_columns(table):
        if row.get('name') == name:
            return row
    return None


def _ensure_numeric_quantity(inspector, table, column):
    row = _column(inspector, table, column)
    if not row:
        return
    current = row.get('type')
    if isinstance(current, sa.Numeric) and getattr(current, 'scale', None) == 3:
        return
    op.alter_column(
        table, column, existing_type=current, type_=QTY,
        existing_nullable=bool(row.get('nullable', True)),
    )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if 'company_retail_settings' not in tables:
        op.create_table(
            'company_retail_settings',
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), primary_key=True),
            sa.Column('industry_profile', sa.String(30), nullable=False, server_default='GENERAL'),
            sa.Column('enable_variants', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('enable_uom', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('enable_price_lists', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('enable_lots', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('enable_serials', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('enable_expirations', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('enable_warranties', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('enable_bundles', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('enable_credit', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('enable_loyalty', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('enable_gift_cards', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('enable_terminals', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('enable_layaway', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('enable_replenishment', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('costing_method', sa.String(20), nullable=False, server_default='AVERAGE'),
            sa.Column('default_receipt_width', sa.Integer(), nullable=False, server_default='80'),
            sa.Column('loyalty_points_per_currency', sa.Numeric(12, 4), nullable=False, server_default='0'),
            sa.Column('loyalty_currency_per_point', sa.Numeric(12, 4), nullable=False, server_default='0'),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.CheckConstraint("industry_profile IN ('GENERAL','FASHION','TECH','HARDWARE','GROCERY','DISTRIBUTION','COSMETICS','FURNITURE','OTHER')", name='ck_retail_profile'),
            sa.CheckConstraint("costing_method IN ('AVERAGE','FIFO','LAST')", name='ck_retail_costing_method'),
            sa.CheckConstraint('default_receipt_width IN (58,80)', name='ck_retail_receipt_width'),
            sa.CheckConstraint('loyalty_points_per_currency >= 0 AND loyalty_currency_per_point >= 0', name='ck_retail_loyalty_rates'),
        )

    if 'branches' not in tables:
        op.create_table(
            'branches',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('code', sa.String(30), nullable=False),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('address', sa.String(255)),
            sa.Column('phone', sa.String(40)),
            sa.Column('status', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('is_main', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id', 'code', name='uq_branch_company_code'),
        )
        op.create_index('ix_branches_company_id', 'branches', ['company_id'])

    if 'units_of_measure' not in tables:
        op.create_table(
            'units_of_measure',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('name', sa.String(80), nullable=False),
            sa.Column('symbol', sa.String(20), nullable=False),
            sa.Column('category', sa.String(40), nullable=False, server_default='UNIT'),
            sa.Column('factor_to_reference', FACTOR, nullable=False, server_default='1'),
            sa.Column('rounding', sa.Numeric(12, 6), nullable=False, server_default='1'),
            sa.Column('allow_fraction', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id', 'name', 'category', name='uq_uom_company_name_category'),
            sa.CheckConstraint('factor_to_reference > 0', name='ck_uom_factor_positive'),
            sa.CheckConstraint('rounding > 0', name='ck_uom_rounding_positive'),
        )
        op.create_index('ix_units_of_measure_company_id', 'units_of_measure', ['company_id'])

    if 'price_lists' not in tables:
        op.create_table(
            'price_lists',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('code', sa.String(30), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('currency_code', sa.String(3), nullable=False, server_default='DOP'),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id', 'code', name='uq_price_list_company_code'),
        )
        op.create_index('ix_price_lists_company_id', 'price_lists', ['company_id'])

    if 'pos_terminals' not in tables:
        op.create_table(
            'pos_terminals',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
            sa.Column('code', sa.String(30), nullable=False),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('receipt_width', sa.Integer(), nullable=False, server_default='80'),
            sa.Column('status', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id', 'code', name='uq_terminal_company_code'),
            sa.CheckConstraint('receipt_width IN (58,80)', name='ck_terminal_receipt_width'),
        )
        op.create_index('ix_pos_terminals_company_id', 'pos_terminals', ['company_id'])
        op.create_index('ix_pos_terminals_branch_id', 'pos_terminals', ['branch_id'])
        op.create_index('ix_pos_terminals_warehouse_id', 'pos_terminals', ['warehouse_id'])

    # Repair SQL-level defaults when an older 2026.08.2 startup pre-created
    # Retail tables through db.create_all(). ORM `default=` values are not
    # PostgreSQL server defaults, so raw migration INSERTs would otherwise fail
    # on NOT NULL columns. These ALTERs are idempotent and safe on fresh tables.
    for table, defaults in {
        'company_retail_settings': {
            'industry_profile': sa.text("'GENERAL'"),
            'enable_variants': sa.true(),
            'enable_uom': sa.true(),
            'enable_price_lists': sa.true(),
            'enable_lots': sa.false(),
            'enable_serials': sa.false(),
            'enable_expirations': sa.false(),
            'enable_warranties': sa.false(),
            'enable_bundles': sa.true(),
            'enable_credit': sa.true(),
            'enable_loyalty': sa.false(),
            'enable_gift_cards': sa.false(),
            'enable_terminals': sa.true(),
            'enable_layaway': sa.false(),
            'enable_replenishment': sa.true(),
            'costing_method': sa.text("'AVERAGE'"),
            'default_receipt_width': sa.text('80'),
            'loyalty_points_per_currency': sa.text('0'),
            'loyalty_currency_per_point': sa.text('0'),
            'updated_at': sa.text('CURRENT_TIMESTAMP'),
        },
        'branches': {
            'status': sa.true(),
            'is_main': sa.false(),
            'created_at': sa.text('CURRENT_TIMESTAMP'),
        },
        'units_of_measure': {
            'category': sa.text("'UNIT'"),
            'factor_to_reference': sa.text('1'),
            'rounding': sa.text('1'),
            'allow_fraction': sa.false(),
            'active': sa.true(),
            'created_at': sa.text('CURRENT_TIMESTAMP'),
        },
        'price_lists': {
            'currency_code': sa.text("'DOP'"),
            'is_default': sa.false(),
            'active': sa.true(),
            'created_at': sa.text('CURRENT_TIMESTAMP'),
        },
    }.items():
        existing = _cols(sa.inspect(bind), table)
        for column_name, server_default in defaults.items():
            if column_name in existing:
                op.alter_column(table, column_name, server_default=server_default)

    # Existing master columns.
    inspector = sa.inspect(bind)
    cols = _cols(inspector, 'products')
    for name, column in [
        ('brand', sa.Column('brand', sa.String(100))),
        ('sale_mode', sa.Column('sale_mode', sa.String(20), nullable=False, server_default='UNIT')),
        ('tracking', sa.Column('tracking', sa.String(20), nullable=False, server_default='NONE')),
        ('warranty_days', sa.Column('warranty_days', sa.Integer(), nullable=False, server_default='0')),
        ('base_uom_id', sa.Column('base_uom_id', sa.Integer(), sa.ForeignKey('units_of_measure.id'))),
        ('sale_uom_id', sa.Column('sale_uom_id', sa.Integer(), sa.ForeignKey('units_of_measure.id'))),
        ('purchase_uom_id', sa.Column('purchase_uom_id', sa.Integer(), sa.ForeignKey('units_of_measure.id'))),
    ]:
        if name not in cols:
            op.add_column('products', column)
    product_checks = _checks(sa.inspect(bind), 'products')
    if 'ck_products_sale_mode' not in product_checks:
        op.create_check_constraint('ck_products_sale_mode', 'products', "sale_mode IN ('UNIT','WEIGHT')")
    if 'ck_products_tracking' not in product_checks:
        op.create_check_constraint('ck_products_tracking', 'products', "tracking IN ('NONE','LOT','SERIAL')")
    if 'ck_products_warranty_days' not in product_checks:
        op.create_check_constraint('ck_products_warranty_days', 'products', 'warranty_days >= 0')

    cols = _cols(sa.inspect(bind), 'clients')
    for name, column in [
        ('price_list_id', sa.Column('price_list_id', sa.Integer(), sa.ForeignKey('price_lists.id'))),
        ('credit_enabled', sa.Column('credit_enabled', sa.Boolean(), nullable=False, server_default=sa.false())),
        ('credit_limit', sa.Column('credit_limit', MONEY, nullable=False, server_default='0')),
        ('payment_terms_days', sa.Column('payment_terms_days', sa.Integer(), nullable=False, server_default='0')),
        ('credit_hold', sa.Column('credit_hold', sa.Boolean(), nullable=False, server_default=sa.false())),
        ('loyalty_points', sa.Column('loyalty_points', QTY, nullable=False, server_default='0')),
    ]:
        if name not in cols:
            op.add_column('clients', column)
    if 'ck_clients_credit_values' not in _checks(sa.inspect(bind), 'clients'):
        op.create_check_constraint('ck_clients_credit_values', 'clients', 'credit_limit >= 0 AND payment_terms_days >= 0 AND loyalty_points >= 0')

    cols = _cols(sa.inspect(bind), 'warehouses')
    if 'branch_id' not in cols:
        op.add_column('warehouses', sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')))
        op.create_index('ix_warehouses_branch_id', 'warehouses', ['branch_id'])

    cols = _cols(sa.inspect(bind), 'users')
    if 'branch_id' not in cols:
        op.add_column('users', sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')))
    if 'terminal_id' not in cols:
        op.add_column('users', sa.Column('terminal_id', sa.Integer(), sa.ForeignKey('pos_terminals.id')))

    sales_checks = _checks(sa.inspect(bind), 'sales')
    if 'ck_sales_status' in sales_checks:
        op.drop_constraint('ck_sales_status', 'sales', type_='check')
    op.create_check_constraint('ck_sales_status', 'sales', "status IN ('DRAFT','PENDING','QUOTATION','LAYAWAY','COMPLETED','CANCELLED')")

    cols = _cols(sa.inspect(bind), 'sales')
    for name, column in [
        ('branch_id', sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'))),
        ('terminal_id', sa.Column('terminal_id', sa.Integer(), sa.ForeignKey('pos_terminals.id'))),
        ('price_list_id', sa.Column('price_list_id', sa.Integer(), sa.ForeignKey('price_lists.id'))),
    ]:
        if name not in cols:
            op.add_column('sales', column)
            op.create_index(f'ix_sales_{name}', 'sales', [name])

    if 'product_attributes' not in tables:
        op.create_table(
            'product_attributes',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('name', sa.String(80), nullable=False),
            sa.Column('display_type', sa.String(20), nullable=False, server_default='SELECT'),
            sa.Column('sequence', sa.Integer(), nullable=False, server_default='10'),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint('company_id', 'name', name='uq_product_attribute_company_name'),
        )
        op.create_index('ix_product_attributes_company_id', 'product_attributes', ['company_id'])

    if 'product_attribute_values' not in tables:
        op.create_table(
            'product_attribute_values',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('attribute_id', sa.Integer(), sa.ForeignKey('product_attributes.id'), nullable=False),
            sa.Column('value', sa.String(80), nullable=False),
            sa.Column('color_hex', sa.String(7)),
            sa.Column('sequence', sa.Integer(), nullable=False, server_default='10'),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint('attribute_id', 'value', name='uq_product_attribute_value'),
        )
        op.create_index('ix_product_attribute_values_company_id', 'product_attribute_values', ['company_id'])
        op.create_index('ix_product_attribute_values_attribute_id', 'product_attribute_values', ['attribute_id'])

    if 'product_variants' not in tables:
        op.create_table(
            'product_variants',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('sku', sa.String(80), nullable=False),
            sa.Column('name', sa.String(180), nullable=False),
            sa.Column('price_extra', MONEY, nullable=False, server_default='0'),
            sa.Column('cost_extra', MONEY, nullable=False, server_default='0'),
            sa.Column('image_path', sa.String(255)),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id', 'sku', name='uq_product_variant_company_sku'),
        )
        op.create_index('ix_product_variants_company_id', 'product_variants', ['company_id'])
        op.create_index('ix_product_variants_product_id', 'product_variants', ['product_id'])

    if 'product_variant_values' not in tables:
        op.create_table(
            'product_variant_values',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id'), nullable=False),
            sa.Column('attribute_value_id', sa.Integer(), sa.ForeignKey('product_attribute_values.id'), nullable=False),
            sa.UniqueConstraint('variant_id', 'attribute_value_id', name='uq_variant_attribute_value'),
        )
        op.create_index('ix_product_variant_values_variant_id', 'product_variant_values', ['variant_id'])
        op.create_index('ix_product_variant_values_attribute_value_id', 'product_variant_values', ['attribute_value_id'])

    if 'product_barcodes' not in tables:
        op.create_table(
            'product_barcodes',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id')),
            sa.Column('code', sa.String(120), nullable=False),
            sa.Column('barcode_type', sa.String(20), nullable=False, server_default='CODE128'),
            sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id', 'code', name='uq_product_barcode_company_code'),
            sa.CheckConstraint("barcode_type IN ('EAN13','EAN8','UPC','CODE128','QR','INTERNAL','SUPPLIER')", name='ck_product_barcode_type'),
        )
        op.create_index('ix_product_barcodes_company_id', 'product_barcodes', ['company_id'])
        op.create_index('ix_product_barcodes_product_id', 'product_barcodes', ['product_id'])
        op.create_index('ix_product_barcodes_variant_id', 'product_barcodes', ['variant_id'])

    if 'warehouse_variant_stock' not in tables:
        op.create_table(
            'warehouse_variant_stock',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id'), nullable=False),
            sa.Column('quantity', QTY, nullable=False, server_default='0'),
            sa.UniqueConstraint('company_id', 'warehouse_id', 'variant_id', name='uq_warehouse_variant_stock'),
            sa.CheckConstraint('quantity >= 0', name='ck_warehouse_variant_stock_nonnegative'),
        )
        for c in ('company_id','warehouse_id','product_id','variant_id'):
            op.create_index(f'ix_warehouse_variant_stock_{c}', 'warehouse_variant_stock', [c])

    if 'price_list_rules' not in tables:
        op.create_table(
            'price_list_rules',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('price_list_id', sa.Integer(), sa.ForeignKey('price_lists.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id')),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id')),
            sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id')),
            sa.Column('min_quantity', QTY, nullable=False, server_default='1'),
            sa.Column('rule_type', sa.String(20), nullable=False, server_default='FIXED'),
            sa.Column('fixed_price', MONEY),
            sa.Column('percent', sa.Numeric(7, 3)),
            sa.Column('starts_at', sa.DateTime()),
            sa.Column('ends_at', sa.DateTime()),
            sa.Column('priority', sa.Integer(), nullable=False, server_default='10'),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.CheckConstraint('min_quantity > 0', name='ck_price_rule_qty_positive'),
            sa.CheckConstraint("rule_type IN ('FIXED','DISCOUNT','SURCHARGE')", name='ck_price_rule_type'),
        )
        for c in ('company_id','price_list_id','product_id','variant_id','category_id'):
            op.create_index(f'ix_price_list_rules_{c}', 'price_list_rules', [c])

    if 'product_suppliers' not in tables:
        op.create_table(
            'product_suppliers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id')),
            sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=False),
            sa.Column('supplier_sku', sa.String(80)),
            sa.Column('unit_cost', MONEY, nullable=False, server_default='0'),
            sa.Column('min_quantity', QTY, nullable=False, server_default='1'),
            sa.Column('lead_time_days', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('preferred', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint('company_id','product_id','variant_id','supplier_id', name='uq_product_supplier'),
            sa.CheckConstraint('unit_cost >= 0 AND min_quantity > 0 AND lead_time_days >= 0', name='ck_product_supplier_values'),
        )
        for c in ('company_id','product_id','variant_id','supplier_id'):
            op.create_index(f'ix_product_suppliers_{c}', 'product_suppliers', [c])

    if 'product_bundle_items' not in tables:
        op.create_table(
            'product_bundle_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('bundle_product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('component_product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('component_variant_id', sa.Integer(), sa.ForeignKey('product_variants.id')),
            sa.Column('quantity', QTY, nullable=False, server_default='1'),
            sa.UniqueConstraint('bundle_product_id','component_product_id','component_variant_id', name='uq_bundle_component'),
            sa.CheckConstraint('quantity > 0', name='ck_bundle_item_qty_positive'),
        )
        for c in ('company_id','bundle_product_id','component_product_id'):
            op.create_index(f'ix_product_bundle_items_{c}', 'product_bundle_items', [c])

    if 'inventory_lots' not in tables:
        op.create_table(
            'inventory_lots',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id')),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
            sa.Column('lot_number', sa.String(100), nullable=False),
            sa.Column('quantity', QTY, nullable=False, server_default='0'),
            sa.Column('manufactured_at', sa.Date()),
            sa.Column('expires_at', sa.Date()),
            sa.Column('received_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('status', sa.String(20), nullable=False, server_default='AVAILABLE'),
            sa.UniqueConstraint('company_id','product_id','variant_id','warehouse_id','lot_number', name='uq_inventory_lot'),
            sa.CheckConstraint('quantity >= 0', name='ck_inventory_lot_qty_nonnegative'),
            sa.CheckConstraint("status IN ('AVAILABLE','QUARANTINE','EXPIRED','DEPLETED')", name='ck_inventory_lot_status'),
        )
        for c in ('company_id','product_id','variant_id','warehouse_id','expires_at'):
            op.create_index(f'ix_inventory_lots_{c}', 'inventory_lots', [c])

    # Sale / purchase line extensions and quantity precision.
    cols = _cols(sa.inspect(bind), 'sale_items')
    for name, column in [
        ('variant_id', sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id'))),
        ('uom_id', sa.Column('uom_id', sa.Integer(), sa.ForeignKey('units_of_measure.id'))),
        ('uom_factor', sa.Column('uom_factor', FACTOR, nullable=False, server_default='1')),
        ('cost_snapshot', sa.Column('cost_snapshot', sa.Numeric(12,4), nullable=False, server_default='0')),
    ]:
        if name not in cols:
            op.add_column('sale_items', column)
    _ensure_numeric_quantity(sa.inspect(bind), 'sale_items', 'quantity')
    if 'ix_sale_items_variant_id' not in _indexes(sa.inspect(bind), 'sale_items'):
        op.create_index('ix_sale_items_variant_id', 'sale_items', ['variant_id'])

    cols = _cols(sa.inspect(bind), 'purchase_order_items')
    for name, column in [
        ('variant_id', sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id'))),
        ('uom_id', sa.Column('uom_id', sa.Integer(), sa.ForeignKey('units_of_measure.id'))),
        ('uom_factor', sa.Column('uom_factor', FACTOR, nullable=False, server_default='1')),
    ]:
        if name not in cols:
            op.add_column('purchase_order_items', column)
    for col in ('quantity','quantity_received'):
        _ensure_numeric_quantity(sa.inspect(bind), 'purchase_order_items', col)

    # Change all inventory quantity columns to 3-decimal precision.
    for table, columns in {
        'warehouse_stock': ['quantity'],
        'stock_movements': ['quantity'],
        'stock_transfers': ['quantity'],
        'location_stock': ['quantity'],
        'location_movements': ['quantity','balance_after'],
        'sale_return_items': ['quantity'],
        'inventory_count_items': ['expected_quantity','counted_quantity'],
        'purchase_return_items': ['quantity'],
    }.items():
        if table in set(sa.inspect(bind).get_table_names()):
            for col in columns:
                if col in _cols(sa.inspect(bind), table):
                    _ensure_numeric_quantity(sa.inspect(bind), table, col)

    if 'inventory_serials' not in tables:
        op.create_table(
            'inventory_serials',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id')),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id')),
            sa.Column('serial_number', sa.String(120), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='AVAILABLE'),
            sa.Column('acquired_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('sold_at', sa.DateTime()),
            sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id')),
            sa.Column('warranty_until', sa.Date()),
            sa.Column('notes', sa.String(255)),
            sa.UniqueConstraint('company_id','serial_number', name='uq_inventory_serial_company_number'),
            sa.CheckConstraint("status IN ('AVAILABLE','RESERVED','SOLD','WARRANTY','SCRAPPED')", name='ck_inventory_serial_status'),
        )
        for c in ('company_id','product_id','variant_id','warehouse_id','sale_item_id'):
            op.create_index(f'ix_inventory_serials_{c}', 'inventory_serials', [c])

    if 'sale_item_lot_allocations' not in tables:
        op.create_table(
            'sale_item_lot_allocations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id'), nullable=False),
            sa.Column('lot_id', sa.Integer(), sa.ForeignKey('inventory_lots.id'), nullable=False),
            sa.Column('quantity', QTY, nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('sale_item_id','lot_id', name='uq_sale_item_lot'),
            sa.CheckConstraint('quantity > 0', name='ck_sale_item_lot_qty_positive'),
        )
        op.create_index('ix_sale_item_lot_allocations_company_id', 'sale_item_lot_allocations', ['company_id'])
        op.create_index('ix_sale_item_lot_allocations_sale_item_id', 'sale_item_lot_allocations', ['sale_item_id'])
        op.create_index('ix_sale_item_lot_allocations_lot_id', 'sale_item_lot_allocations', ['lot_id'])

    if 'warranty_claims' not in tables:
        op.create_table(
            'warranty_claims',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('serial_id', sa.Integer(), sa.ForeignKey('inventory_serials.id')),
            sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id'), nullable=False),
            sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id')),
            sa.Column('status', sa.String(20), nullable=False, server_default='OPEN'),
            sa.Column('reason', sa.String(255), nullable=False),
            sa.Column('resolution', sa.String(255)),
            sa.Column('opened_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('closed_at', sa.DateTime()),
            sa.CheckConstraint("status IN ('OPEN','IN_REVIEW','APPROVED','REPLACED','REPAIRED','REJECTED','CLOSED')", name='ck_warranty_claim_status'),
        )
        for c in ('company_id','serial_id','sale_item_id','client_id'):
            op.create_index(f'ix_warranty_claims_{c}', 'warranty_claims', [c])

    if 'gift_cards' not in tables:
        op.create_table(
            'gift_cards',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id')),
            sa.Column('code', sa.String(80), nullable=False),
            sa.Column('initial_balance', MONEY, nullable=False),
            sa.Column('balance', MONEY, nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='ACTIVE'),
            sa.Column('expires_at', sa.Date()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id','code', name='uq_gift_card_company_code'),
            sa.CheckConstraint('initial_balance >= 0 AND balance >= 0', name='ck_gift_card_balance'),
            sa.CheckConstraint("status IN ('ACTIVE','BLOCKED','EXPIRED','DEPLETED')", name='ck_gift_card_status'),
        )
        op.create_index('ix_gift_cards_company_id', 'gift_cards', ['company_id'])
        op.create_index('ix_gift_cards_client_id', 'gift_cards', ['client_id'])

    if 'sale_payments' not in tables:
        op.create_table(
            'sale_payments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id'), nullable=False),
            sa.Column('method', sa.String(20), nullable=False),
            sa.Column('amount', MONEY, nullable=False),
            sa.Column('reference', sa.String(120)),
            sa.Column('gift_card_id', sa.Integer(), sa.ForeignKey('gift_cards.id')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.CheckConstraint('amount > 0', name='ck_sale_payment_amount_positive'),
            sa.CheckConstraint("method IN ('CASH','CARD','TRANSFER','CREDIT','GIFT_CARD','OTHER')", name='ck_sale_payment_method'),
        )
        op.create_index('ix_sale_payments_company_id', 'sale_payments', ['company_id'])
        op.create_index('ix_sale_payments_sale_id', 'sale_payments', ['sale_id'])

    if 'loyalty_transactions' not in tables:
        op.create_table(
            'loyalty_transactions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
            sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id')),
            sa.Column('event_type', sa.String(20), nullable=False),
            sa.Column('points', QTY, nullable=False),
            sa.Column('balance_after', QTY, nullable=False),
            sa.Column('notes', sa.String(255)),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.CheckConstraint("event_type IN ('EARN','REDEEM','ADJUST','EXPIRE')", name='ck_loyalty_event_type'),
        )
        for c in ('company_id','client_id','sale_id'):
            op.create_index(f'ix_loyalty_transactions_{c}', 'loyalty_transactions', [c])

    if 'layaways' not in tables:
        op.create_table(
            'layaways',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id'), nullable=False),
            sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
            sa.Column('deposit_amount', MONEY, nullable=False, server_default='0'),
            sa.Column('balance', MONEY, nullable=False, server_default='0'),
            sa.Column('due_date', sa.Date()),
            sa.Column('status', sa.String(20), nullable=False, server_default='OPEN'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('completed_at', sa.DateTime()),
            sa.UniqueConstraint('sale_id', name='uq_layaway_sale'),
            sa.CheckConstraint("status IN ('OPEN','COMPLETED','CANCELLED','EXPIRED')", name='ck_layaway_status'),
            sa.CheckConstraint('deposit_amount >= 0 AND balance >= 0', name='ck_layaway_amounts'),
        )
        for c in ('company_id','sale_id','client_id'):
            op.create_index(f'ix_layaways_{c}', 'layaways', [c])

    if 'layaway_payments' not in tables:
        op.create_table(
            'layaway_payments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('layaway_id', sa.Integer(), sa.ForeignKey('layaways.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('amount', MONEY, nullable=False),
            sa.Column('method', sa.String(20), nullable=False, server_default='CASH'),
            sa.Column('reference', sa.String(120)),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.CheckConstraint('amount > 0', name='ck_layaway_payment_amount_positive'),
        )
        op.create_index('ix_layaway_payments_company_id', 'layaway_payments', ['company_id'])
        op.create_index('ix_layaway_payments_layaway_id', 'layaway_payments', ['layaway_id'])

    if 'stock_reservations' not in tables:
        op.create_table(
            'stock_reservations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id')),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
            sa.Column('quantity', QTY, nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='ACTIVE'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id','sale_item_id', name='uq_stock_reservation_sale_item'),
            sa.CheckConstraint('quantity > 0', name='ck_stock_reservation_qty_positive'),
            sa.CheckConstraint("status IN ('ACTIVE','RELEASED','CONSUMED')", name='ck_stock_reservation_status'),
        )
        for c in ('company_id','sale_item_id','product_id','variant_id','warehouse_id'):
            op.create_index(f'ix_stock_reservations_{c}', 'stock_reservations', [c])

    if 'approval_rules' not in tables:
        op.create_table(
            'approval_rules',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('operation_type', sa.String(30), nullable=False),
            sa.Column('threshold_amount', MONEY, nullable=False, server_default='0'),
            sa.Column('required_role', sa.String(40), nullable=False, server_default='admin'),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.CheckConstraint("operation_type IN ('DISCOUNT','PURCHASE','STOCK_ADJUST','RETURN','EXPENSE')", name='ck_approval_rule_operation'),
            sa.CheckConstraint('threshold_amount >= 0', name='ck_approval_rule_threshold'),
        )
        op.create_index('ix_approval_rules_company_id', 'approval_rules', ['company_id'])

    if 'approval_requests' not in tables:
        op.create_table(
            'approval_requests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('rule_id', sa.Integer(), sa.ForeignKey('approval_rules.id'), nullable=False),
            sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id')),
            sa.Column('entity_type', sa.String(40), nullable=False),
            sa.Column('entity_id', sa.Integer()),
            sa.Column('amount', MONEY, nullable=False, server_default='0'),
            sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
            sa.Column('reason', sa.String(255)),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('resolved_at', sa.DateTime()),
            sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','CANCELLED')", name='ck_approval_request_status'),
        )
        op.create_index('ix_approval_requests_company_id', 'approval_requests', ['company_id'])

    if 'inventory_cost_layers' not in tables:
        op.create_table(
            'inventory_cost_layers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id')),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
            sa.Column('purchase_item_id', sa.Integer(), sa.ForeignKey('purchase_order_items.id')),
            sa.Column('quantity_remaining', QTY, nullable=False),
            sa.Column('unit_cost', sa.Numeric(12,4), nullable=False),
            sa.Column('received_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.CheckConstraint('quantity_remaining >= 0 AND unit_cost >= 0', name='ck_inventory_cost_layer_values'),
        )
        for c in ('company_id','product_id','variant_id','warehouse_id','purchase_item_id','received_at'):
            op.create_index(f'ix_inventory_cost_layers_{c}', 'inventory_cost_layers', [c])

    if 'api_keys' not in tables:
        op.create_table(
            'api_keys',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('key_prefix', sa.String(16), nullable=False),
            sa.Column('key_hash', sa.String(64), nullable=False),
            sa.Column('scopes', sa.String(500), nullable=False, server_default='products:read,inventory:read'),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('last_used_at', sa.DateTime()),
            sa.Column('expires_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('key_hash', name='uq_api_key_hash'),
        )
        op.create_index('ix_api_keys_company_id', 'api_keys', ['company_id'])
        op.create_index('ix_api_keys_key_prefix', 'api_keys', ['key_prefix'])

    if 'outbound_webhooks' not in tables:
        op.create_table(
            'outbound_webhooks',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('target_url', sa.String(500), nullable=False),
            sa.Column('secret', sa.String(120), nullable=False),
            sa.Column('event_types', sa.String(500), nullable=False, server_default='sale.completed'),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('ix_outbound_webhooks_company_id', 'outbound_webhooks', ['company_id'])

    # Advanced promotion mechanics keep legacy PERCENT/FIXED compatible.
    cols = _cols(sa.inspect(bind), 'promotions')
    for name, column in [
        ('mechanic', sa.Column('mechanic', sa.String(30), nullable=False, server_default='STANDARD')),
        ('scope', sa.Column('scope', sa.String(20), nullable=False, server_default='ALL')),
        ('target_product_id', sa.Column('target_product_id', sa.Integer(), sa.ForeignKey('products.id'))),
        ('target_category_id', sa.Column('target_category_id', sa.Integer(), sa.ForeignKey('categories.id'))),
        ('target_brand', sa.Column('target_brand', sa.String(100))),
        ('buy_qty', sa.Column('buy_qty', QTY, nullable=False, server_default='1')),
        ('reward_qty', sa.Column('reward_qty', QTY, nullable=False, server_default='1')),
        ('reward_percent', sa.Column('reward_percent', sa.Numeric(7,3), nullable=False, server_default='100')),
        ('max_discount', sa.Column('max_discount', MONEY)),
    ]:
        if name not in cols:
            op.add_column('promotions', column)
    promotion_checks = _checks(sa.inspect(bind), 'promotions')
    if 'ck_promotions_mechanic' not in promotion_checks:
        op.create_check_constraint('ck_promotions_mechanic', 'promotions', "mechanic IN ('STANDARD','BUY_X_GET_Y','SECOND_PERCENT')")
    if 'ck_promotions_scope' not in promotion_checks:
        op.create_check_constraint('ck_promotions_scope', 'promotions', "scope IN ('ALL','PRODUCT','CATEGORY','BRAND')")
    if 'ck_promotions_rewards' not in promotion_checks:
        op.create_check_constraint('ck_promotions_rewards', 'promotions', 'buy_qty > 0 AND reward_qty > 0 AND reward_percent >= 0 AND reward_percent <= 100')
    if 'ck_promotions_max_discount' not in promotion_checks:
        op.create_check_constraint('ck_promotions_max_discount', 'promotions', 'max_discount IS NULL OR max_discount >= 0')

    cols = _cols(sa.inspect(bind), 'cash_sessions')
    if 'terminal_id' not in cols:
        op.add_column('cash_sessions', sa.Column('terminal_id', sa.Integer(), sa.ForeignKey('pos_terminals.id')))
        op.create_index('ix_cash_sessions_terminal_id', 'cash_sessions', ['terminal_id'])

    # Bootstrap a main branch and sane units/default price list for every existing tenant.
    op.execute(sa.text("""
        INSERT INTO company_retail_settings (
            company_id, industry_profile, enable_variants, enable_uom,
            enable_price_lists, enable_lots, enable_serials, enable_expirations,
            enable_warranties, enable_bundles, enable_credit, enable_loyalty,
            enable_gift_cards, enable_terminals, enable_layaway,
            enable_replenishment, costing_method, default_receipt_width,
            loyalty_points_per_currency, loyalty_currency_per_point, updated_at
        )
        SELECT id, 'GENERAL', TRUE, TRUE, TRUE, FALSE, FALSE, FALSE, FALSE,
               TRUE, TRUE, FALSE, FALSE, TRUE, FALSE, TRUE, 'AVERAGE', 80,
               0, 0, CURRENT_TIMESTAMP
        FROM companies c
        WHERE NOT EXISTS (SELECT 1 FROM company_retail_settings s WHERE s.company_id = c.id)
    """))
    op.execute(sa.text("""
        INSERT INTO branches (company_id, code, name, status, is_main, created_at)
        SELECT id, 'MAIN', 'Sucursal principal', TRUE, TRUE, CURRENT_TIMESTAMP FROM companies c
        WHERE NOT EXISTS (SELECT 1 FROM branches b WHERE b.company_id = c.id)
    """))
    op.execute(sa.text("""
        UPDATE warehouses w SET branch_id = b.id
        FROM branches b
        WHERE w.company_id = b.company_id AND b.is_main = TRUE AND w.branch_id IS NULL
    """))
    op.execute(sa.text("""
        INSERT INTO price_lists (company_id, code, name, currency_code, is_default, active, created_at)
        SELECT id, 'PUBLIC', 'Precio público', 'DOP', TRUE, TRUE, CURRENT_TIMESTAMP FROM companies c
        WHERE NOT EXISTS (SELECT 1 FROM price_lists p WHERE p.company_id = c.id)
    """))
    # Keep numeric bootstrap parameters explicitly typed. Psycopg 3 otherwise
    # infers Python strings as VARCHAR, and PostgreSQL will not implicitly cast
    # those bind parameters into NUMERIC columns in INSERT ... SELECT.
    uom_seed = sa.text("""
        INSERT INTO units_of_measure (
            company_id, name, symbol, category, factor_to_reference, rounding,
            allow_fraction, active, created_at
        )
        SELECT id, :name, :symbol, :category,
               CAST(:factor AS NUMERIC(18, 6)),
               CAST(:rounding AS NUMERIC(12, 6)),
               CAST(:frac AS BOOLEAN), TRUE, CURRENT_TIMESTAMP
        FROM companies c
        WHERE NOT EXISTS (
            SELECT 1 FROM units_of_measure u
            WHERE u.company_id = c.id AND u.name = :name AND u.category = :category
        )
    """).bindparams(
        sa.bindparam('name', type_=sa.String(80)),
        sa.bindparam('symbol', type_=sa.String(20)),
        sa.bindparam('category', type_=sa.String(40)),
        sa.bindparam('factor', type_=FACTOR),
        sa.bindparam('rounding', type_=sa.Numeric(12, 6)),
        sa.bindparam('frac', type_=sa.Boolean()),
    )
    for name, symbol, category, factor, rounding, frac in [
        ('Unidad', 'ud', 'UNIT', Decimal('1'), Decimal('1'), False),
        ('Caja', 'caja', 'UNIT', Decimal('1'), Decimal('1'), False),
        ('Kilogramo', 'kg', 'WEIGHT', Decimal('1'), Decimal('0.001'), True),
        ('Gramo', 'g', 'WEIGHT', Decimal('0.001'), Decimal('0.001'), True),
        ('Litro', 'L', 'VOLUME', Decimal('1'), Decimal('0.001'), True),
        ('Mililitro', 'ml', 'VOLUME', Decimal('0.001'), Decimal('0.001'), True),
        ('Metro', 'm', 'LENGTH', Decimal('1'), Decimal('0.001'), True),
    ]:
        bind.execute(uom_seed, {
            'name': name,
            'symbol': symbol,
            'category': category,
            'factor': factor,
            'rounding': rounding,
            'frac': frac,
        })
    op.execute(sa.text("""
        UPDATE products p SET base_uom_id = u.id, sale_uom_id = u.id, purchase_uom_id = u.id
        FROM units_of_measure u
        WHERE p.company_id = u.company_id AND u.name = 'Unidad' AND u.category = 'UNIT'
          AND p.base_uom_id IS NULL
    """))


def downgrade():
    # Conservative downgrade: remove optional retail tables/columns. Quantity
    # precision is intentionally not collapsed back to integer to avoid data loss.
    for table in [
        'outbound_webhooks','api_keys','inventory_cost_layers','approval_requests','approval_rules','stock_reservations','layaways',
        'loyalty_transactions','sale_payments','gift_cards','layaway_payments','warranty_claims','sale_item_lot_allocations','inventory_serials','inventory_lots',
        'product_bundle_items','product_suppliers','price_list_rules','warehouse_variant_stock','product_barcodes',
        'product_variant_values','product_variants','product_attribute_values','product_attributes'
    ]:
        try:
            op.drop_table(table)
        except Exception:
            pass
    for table, columns in {
        'cash_sessions':['terminal_id'], 'sale_items':['variant_id','uom_id','uom_factor','cost_snapshot'],
        'purchase_order_items':['variant_id','uom_id','uom_factor'],
        'sales':['branch_id','terminal_id','price_list_id'], 'users':['branch_id','terminal_id'],
        'warehouses':['branch_id'], 'clients':['price_list_id','credit_enabled','credit_limit','payment_terms_days','credit_hold','loyalty_points'],
        'products':['brand','sale_mode','tracking','warranty_days','base_uom_id','sale_uom_id','purchase_uom_id'],
        'promotions':['mechanic','scope','target_product_id','target_category_id','target_brand','buy_qty','reward_qty','reward_percent','max_discount'],
    }.items():
        for col in columns:
            try:
                op.drop_column(table, col)
            except Exception:
                pass
    for table in ['pos_terminals','price_lists','units_of_measure','branches','company_retail_settings']:
        try:
            op.drop_table(table)
        except Exception:
            pass
