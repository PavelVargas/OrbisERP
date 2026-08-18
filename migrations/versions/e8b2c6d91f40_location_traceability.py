"""location stock traceability

Revision ID: e8b2c6d91f40
Revises: d4a9b7c2e610
"""
from alembic import op
import sqlalchemy as sa


revision = 'e8b2c6d91f40'
down_revision = 'd4a9b7c2e610'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'location_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('movement_type', sa.String(length=20), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(length=80), nullable=True),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('transfer_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['location_id'], ['warehouse_locations.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['transfer_id'], ['stock_transfers.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_location_movements_location_created', 'location_movements', ['location_id', 'created_at'])


def downgrade():
    op.drop_index('ix_location_movements_location_created', table_name='location_movements')
    op.drop_table('location_movements')
