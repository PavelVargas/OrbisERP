"""warehouse locations and transfer location tracking

Revision ID: d4a9b7c2e610
Revises: c31e8d7a42b0
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4a9b7c2e610'
down_revision = 'c31e8d7a42b0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if 'warehouse_locations' not in tables:
        op.create_table(
            'warehouse_locations',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=120), nullable=False),
            sa.Column('code', sa.String(length=50), nullable=False),
            sa.Column('barcode', sa.String(length=80), nullable=False),
            sa.Column('description', sa.String(length=255), nullable=True),
            sa.Column('status', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('parent_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
            sa.ForeignKeyConstraint(['parent_id'], ['warehouse_locations.id']),
            sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('company_id', 'barcode', name='uq_location_company_barcode'),
            sa.UniqueConstraint('warehouse_id', 'code', name='uq_location_warehouse_code'),
        )
    if 'location_stock' not in tables:
        op.create_table(
            'location_stock',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('location_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('quantity', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
            sa.ForeignKeyConstraint(['location_id'], ['warehouse_locations.id']),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('location_id', 'product_id', name='uq_location_product_stock'),
        )

    inspector = sa.inspect(bind)
    transfer_columns = {column['name'] for column in inspector.get_columns('stock_transfers')}
    if 'from_location_id' not in transfer_columns:
        op.add_column('stock_transfers', sa.Column('from_location_id', sa.Integer(), nullable=True))
    if 'to_location_id' not in transfer_columns:
        op.add_column('stock_transfers', sa.Column('to_location_id', sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    foreign_key_columns = {
        tuple(key.get('constrained_columns') or ())
        for key in inspector.get_foreign_keys('stock_transfers')
    }
    if ('from_location_id',) not in foreign_key_columns:
        op.create_foreign_key('fk_transfer_from_location', 'stock_transfers', 'warehouse_locations', ['from_location_id'], ['id'])
    if ('to_location_id',) not in foreign_key_columns:
        op.create_foreign_key('fk_transfer_to_location', 'stock_transfers', 'warehouse_locations', ['to_location_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_transfer_to_location', 'stock_transfers', type_='foreignkey')
    op.drop_constraint('fk_transfer_from_location', 'stock_transfers', type_='foreignkey')
    op.drop_column('stock_transfers', 'to_location_id')
    op.drop_column('stock_transfers', 'from_location_id')
    op.drop_table('location_stock')
    op.drop_table('warehouse_locations')
