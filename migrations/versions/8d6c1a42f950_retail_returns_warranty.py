"""retail returns, loyalty payments and warranty lifecycle

Revision ID: 8d6c1a42f950
Revises: 7a9c4e21b6d0
"""
from alembic import op
import sqlalchemy as sa

revision = '8d6c1a42f950'
down_revision = '7a9c4e21b6d0'
branch_labels = None
depends_on = None

QTY = sa.Numeric(14, 3)
FACTOR = sa.Numeric(18, 6)


def _cols(bind, table):
    return {c['name'] for c in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table):
    return {row.get('name') for row in sa.inspect(bind).get_indexes(table)}


def _checks(bind, table):
    return {row.get('name') for row in sa.inspect(bind).get_check_constraints(table)}


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    # Return lines existed before Retail 2.0. Complete their retail metadata so
    # returns preserve the original variant/UOM and can carry a physical disposition.
    cols = _cols(bind, 'sale_return_items')
    for name, column in [
        ('variant_id', sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id'))),
        ('uom_id', sa.Column('uom_id', sa.Integer(), sa.ForeignKey('units_of_measure.id'))),
        ('uom_factor', sa.Column('uom_factor', FACTOR, nullable=False, server_default='1')),
        ('disposition', sa.Column('disposition', sa.String(20), nullable=False, server_default='AVAILABLE')),
    ]:
        if name not in cols:
            op.add_column('sale_return_items', column)
    index_names = _indexes(bind, 'sale_return_items')
    for name in ('variant_id', 'uom_id'):
        index_name = f'ix_sale_return_items_{name}'
        if index_name not in index_names:
            op.create_index(index_name, 'sale_return_items', [name])
    if 'ck_sale_return_item_disposition' not in _checks(bind, 'sale_return_items'):
        op.create_check_constraint(
            'ck_sale_return_item_disposition', 'sale_return_items',
            "disposition IN ('AVAILABLE','QUARANTINE','DAMAGED','NONE')",
        )

    cols = _cols(bind, 'warranty_claims')
    if 'resolved_by' not in cols:
        op.add_column('warranty_claims', sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('users.id')))
    if 'updated_at' not in cols:
        op.add_column('warranty_claims', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))

    # Expand existing check constraints for loyalty payments and quarantine serials.
    if bind.dialect.name == 'postgresql':
        payment_checks = _checks(bind, 'sale_payments')
        if 'ck_sale_payment_method' in payment_checks:
            op.drop_constraint('ck_sale_payment_method', 'sale_payments', type_='check')
        op.create_check_constraint(
            'ck_sale_payment_method', 'sale_payments',
            "method IN ('CASH','CARD','TRANSFER','CREDIT','GIFT_CARD','LOYALTY','OTHER')",
        )
        serial_checks = _checks(bind, 'inventory_serials')
        if 'ck_inventory_serial_status' in serial_checks:
            op.drop_constraint('ck_inventory_serial_status', 'inventory_serials', type_='check')
        op.create_check_constraint(
            'ck_inventory_serial_status', 'inventory_serials',
            "status IN ('AVAILABLE','RESERVED','SOLD','WARRANTY','QUARANTINE','SCRAPPED')",
        )

    if 'inventory_condition_stock' not in tables:
        op.create_table(
            'inventory_condition_stock',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id')),
            sa.Column('condition', sa.String(20), nullable=False),
            sa.Column('quantity', QTY, nullable=False, server_default='0'),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id', 'warehouse_id', 'product_id', 'variant_id', 'condition', name='uq_inventory_condition_stock'),
            sa.CheckConstraint('quantity >= 0', name='ck_inventory_condition_stock_nonnegative'),
            sa.CheckConstraint("condition IN ('QUARANTINE','DAMAGED')", name='ck_inventory_condition_stock_condition'),
        )
        for name in ('company_id', 'warehouse_id', 'product_id', 'variant_id'):
            op.create_index(f'ix_inventory_condition_stock_{name}', 'inventory_condition_stock', [name])

    if 'sale_return_item_lot_allocations' not in tables:
        op.create_table(
            'sale_return_item_lot_allocations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('return_item_id', sa.Integer(), sa.ForeignKey('sale_return_items.id'), nullable=False),
            sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id'), nullable=False),
            sa.Column('lot_id', sa.Integer(), sa.ForeignKey('inventory_lots.id'), nullable=False),
            sa.Column('quantity', QTY, nullable=False),
            sa.Column('disposition', sa.String(20), nullable=False, server_default='AVAILABLE'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('return_item_id', 'lot_id', name='uq_return_item_lot'),
            sa.CheckConstraint('quantity > 0', name='ck_return_item_lot_qty_positive'),
            sa.CheckConstraint("disposition IN ('AVAILABLE','QUARANTINE','DAMAGED','NONE')", name='ck_return_item_lot_disposition'),
        )
        for name in ('company_id', 'return_item_id', 'sale_item_id', 'lot_id'):
            op.create_index(f'ix_sale_return_item_lot_allocations_{name}', 'sale_return_item_lot_allocations', [name])

    if 'sale_return_item_serials' not in tables:
        op.create_table(
            'sale_return_item_serials',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('return_item_id', sa.Integer(), sa.ForeignKey('sale_return_items.id'), nullable=False),
            sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id'), nullable=False),
            sa.Column('serial_id', sa.Integer(), sa.ForeignKey('inventory_serials.id'), nullable=False),
            sa.Column('disposition', sa.String(20), nullable=False, server_default='AVAILABLE'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('return_item_id', 'serial_id', name='uq_return_item_serial'),
            sa.CheckConstraint("disposition IN ('AVAILABLE','QUARANTINE','DAMAGED','NONE')", name='ck_return_item_serial_disposition'),
        )
        for name in ('company_id', 'return_item_id', 'sale_item_id', 'serial_id'):
            op.create_index(f'ix_sale_return_item_serials_{name}', 'sale_return_item_serials', [name])

    if 'inventory_serial_events' not in tables:
        op.create_table(
            'inventory_serial_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('serial_id', sa.Integer(), sa.ForeignKey('inventory_serials.id'), nullable=False),
            sa.Column('event_type', sa.String(30), nullable=False),
            sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id')),
            sa.Column('return_item_id', sa.Integer(), sa.ForeignKey('sale_return_items.id')),
            sa.Column('warranty_claim_id', sa.Integer(), sa.ForeignKey('warranty_claims.id')),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id')),
            sa.Column('notes', sa.String(255)),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.CheckConstraint(
                "event_type IN ('RECEIVED','RESERVED','SOLD','RETURNED','WARRANTY_OPEN','WARRANTY_UPDATE','ADJUSTED')",
                name='ck_inventory_serial_event_type',
            ),
        )
        for name in ('company_id', 'serial_id', 'sale_item_id', 'return_item_id', 'warranty_claim_id', 'warehouse_id'):
            op.create_index(f'ix_inventory_serial_events_{name}', 'inventory_serial_events', [name])


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table in ('inventory_serial_events', 'sale_return_item_serials', 'sale_return_item_lot_allocations', 'inventory_condition_stock'):
        if table in tables:
            op.drop_table(table)
    if 'warranty_claims' in tables:
        cols = _cols(bind, 'warranty_claims')
        if 'updated_at' in cols:
            op.drop_column('warranty_claims', 'updated_at')
        if 'resolved_by' in cols:
            op.drop_column('warranty_claims', 'resolved_by')
    if 'sale_return_items' in tables:
        checks = _checks(bind, 'sale_return_items')
        if 'ck_sale_return_item_disposition' in checks:
            op.drop_constraint('ck_sale_return_item_disposition', 'sale_return_items', type_='check')
        indexes = _indexes(bind, 'sale_return_items')
        for name in ('variant_id', 'uom_id'):
            index_name = f'ix_sale_return_items_{name}'
            if index_name in indexes:
                op.drop_index(index_name, table_name='sale_return_items')
        cols = _cols(bind, 'sale_return_items')
        for column in ('disposition', 'uom_factor', 'uom_id', 'variant_id'):
            if column in cols:
                op.drop_column('sale_return_items', column)
    if bind.dialect.name == 'postgresql':
        payment_checks = _checks(bind, 'sale_payments')
        if 'ck_sale_payment_method' in payment_checks:
            op.drop_constraint('ck_sale_payment_method', 'sale_payments', type_='check')
        op.create_check_constraint('ck_sale_payment_method', 'sale_payments', "method IN ('CASH','CARD','TRANSFER','CREDIT','GIFT_CARD','OTHER')")
        serial_checks = _checks(bind, 'inventory_serials')
        if 'ck_inventory_serial_status' in serial_checks:
            op.drop_constraint('ck_inventory_serial_status', 'inventory_serials', type_='check')
        op.create_check_constraint('ck_inventory_serial_status', 'inventory_serials', "status IN ('AVAILABLE','RESERVED','SOLD','WARRANTY','SCRAPPED')")
