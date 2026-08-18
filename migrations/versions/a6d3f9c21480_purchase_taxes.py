"""purchase taxes per line

Revision ID: a6d3f9c21480
Revises: f4c19a72d830
"""
from alembic import op
import sqlalchemy as sa


revision = 'a6d3f9c21480'
down_revision = 'f4c19a72d830'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if 'purchase_taxes' not in tables:
        op.create_table(
            'purchase_taxes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=80), nullable=False),
            sa.Column('rate', sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column('price_included', sa.Boolean(), nullable=False),
            sa.Column('active', sa.Boolean(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('company_id', 'name', name='uq_purchase_tax_company_name'),
        )
    order_columns = {column['name'] for column in inspector.get_columns('purchase_orders')}
    if 'subtotal' not in order_columns:
        op.add_column('purchase_orders', sa.Column('subtotal', sa.Numeric(12, 2), server_default='0'))
    if 'tax_total' not in order_columns:
        op.add_column('purchase_orders', sa.Column('tax_total', sa.Numeric(12, 2), server_default='0'))
    item_columns = {column['name'] for column in inspector.get_columns('purchase_order_items')}
    if 'tax_name' not in item_columns:
        op.add_column('purchase_order_items', sa.Column('tax_name', sa.String(80), nullable=False, server_default='Exento'))
    if 'tax_rate' not in item_columns:
        op.add_column('purchase_order_items', sa.Column('tax_rate', sa.Numeric(5, 2), nullable=False, server_default='0'))
    if 'tax_included' not in item_columns:
        op.add_column('purchase_order_items', sa.Column('tax_included', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute('UPDATE purchase_orders SET subtotal = COALESCE(total_cost, 0), tax_total = 0')


def downgrade():
    op.drop_column('purchase_order_items', 'tax_included')
    op.drop_column('purchase_order_items', 'tax_rate')
    op.drop_column('purchase_order_items', 'tax_name')
    op.drop_column('purchase_orders', 'tax_total')
    op.drop_column('purchase_orders', 'subtotal')
    op.drop_table('purchase_taxes')
