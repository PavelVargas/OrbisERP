"""product-specific UOM conversions and warranty replacements

Revision ID: 9f4a2c7e1b33
Revises: 8d6c1a42f950
"""
from alembic import op
import sqlalchemy as sa

revision = '9f4a2c7e1b33'
down_revision = '8d6c1a42f950'
branch_labels = None
depends_on = None


def _cols(bind, table):
    return {c['name'] for c in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table):
    return {row.get('name') for row in sa.inspect(bind).get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if 'product_uom_conversions' not in tables:
        op.create_table(
            'product_uom_conversions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('uom_id', sa.Integer(), sa.ForeignKey('units_of_measure.id'), nullable=False),
            sa.Column('factor_to_base', sa.Numeric(18, 6), nullable=False, server_default='1'),
            sa.Column('allow_sale', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('allow_purchase', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('company_id', 'product_id', 'uom_id', name='uq_product_uom_conversion'),
            sa.CheckConstraint('factor_to_base > 0', name='ck_product_uom_factor_positive'),
        )
        for name in ('company_id', 'product_id', 'uom_id'):
            op.create_index(f'ix_product_uom_conversions_{name}', 'product_uom_conversions', [name])

    if 'warranty_claims' in tables:
        cols = _cols(bind, 'warranty_claims')
        if 'replacement_serial_id' not in cols:
            op.add_column('warranty_claims', sa.Column('replacement_serial_id', sa.Integer(), sa.ForeignKey('inventory_serials.id')))
        indexes = _indexes(bind, 'warranty_claims')
        if 'ix_warranty_claims_replacement_serial_id' not in indexes:
            op.create_index('ix_warranty_claims_replacement_serial_id', 'warranty_claims', ['replacement_serial_id'])


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if 'warranty_claims' in tables:
        indexes = _indexes(bind, 'warranty_claims')
        if 'ix_warranty_claims_replacement_serial_id' in indexes:
            op.drop_index('ix_warranty_claims_replacement_serial_id', table_name='warranty_claims')
        if 'replacement_serial_id' in _cols(bind, 'warranty_claims'):
            op.drop_column('warranty_claims', 'replacement_serial_id')
    if 'product_uom_conversions' in tables:
        op.drop_table('product_uom_conversions')
