"""attribute inventory and transfer operations to users

Revision ID: f5a9c2d8e641
Revises: e3f8b61c2a74
"""
from alembic import op
import sqlalchemy as sa

revision = 'f5a9c2d8e641'
down_revision = 'e3f8b61c2a74'
branch_labels = None
depends_on = None


def _column_names(inspector, table):
    return {column['name'] for column in inspector.get_columns(table)}


def _index_names(inspector, table):
    return {index['name'] for index in inspector.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if 'stock_movements' in tables:
        columns = _column_names(inspector, 'stock_movements')
        if 'user_id' not in columns:
            op.add_column('stock_movements', sa.Column('user_id', sa.Integer(), nullable=True))
            op.create_foreign_key('fk_stock_movements_user_id_users', 'stock_movements', 'users', ['user_id'], ['id'])
        inspector = sa.inspect(bind)
        if 'ix_stock_movements_user_id' not in _index_names(inspector, 'stock_movements'):
            op.create_index('ix_stock_movements_user_id', 'stock_movements', ['user_id'])

    if 'stock_transfers' in tables:
        columns = _column_names(inspector, 'stock_transfers')
        if 'created_by_id' not in columns:
            op.add_column('stock_transfers', sa.Column('created_by_id', sa.Integer(), nullable=True))
            op.create_foreign_key('fk_stock_transfers_created_by_users', 'stock_transfers', 'users', ['created_by_id'], ['id'])
        if 'received_by_id' not in columns:
            op.add_column('stock_transfers', sa.Column('received_by_id', sa.Integer(), nullable=True))
            op.create_foreign_key('fk_stock_transfers_received_by_users', 'stock_transfers', 'users', ['received_by_id'], ['id'])
        inspector = sa.inspect(bind)
        indexes = _index_names(inspector, 'stock_transfers')
        if 'ix_stock_transfers_created_by_id' not in indexes:
            op.create_index('ix_stock_transfers_created_by_id', 'stock_transfers', ['created_by_id'])
        if 'ix_stock_transfers_received_by_id' not in indexes:
            op.create_index('ix_stock_transfers_received_by_id', 'stock_transfers', ['received_by_id'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if 'stock_transfers' in tables:
        columns = _column_names(inspector, 'stock_transfers')
        indexes = _index_names(inspector, 'stock_transfers')
        if 'ix_stock_transfers_received_by_id' in indexes:
            op.drop_index('ix_stock_transfers_received_by_id', table_name='stock_transfers')
        if 'ix_stock_transfers_created_by_id' in indexes:
            op.drop_index('ix_stock_transfers_created_by_id', table_name='stock_transfers')
        if 'received_by_id' in columns:
            op.drop_constraint('fk_stock_transfers_received_by_users', 'stock_transfers', type_='foreignkey')
            op.drop_column('stock_transfers', 'received_by_id')
        if 'created_by_id' in columns:
            op.drop_constraint('fk_stock_transfers_created_by_users', 'stock_transfers', type_='foreignkey')
            op.drop_column('stock_transfers', 'created_by_id')
    if 'stock_movements' in tables:
        columns = _column_names(inspector, 'stock_movements')
        indexes = _index_names(inspector, 'stock_movements')
        if 'ix_stock_movements_user_id' in indexes:
            op.drop_index('ix_stock_movements_user_id', table_name='stock_movements')
        if 'user_id' in columns:
            op.drop_constraint('fk_stock_movements_user_id_users', 'stock_movements', type_='foreignkey')
            op.drop_column('stock_movements', 'user_id')
