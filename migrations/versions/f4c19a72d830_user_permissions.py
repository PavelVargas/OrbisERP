"""granular user permissions

Revision ID: f4c19a72d830
Revises: e8b2c6d91f40
"""
from alembic import op
import sqlalchemy as sa


revision = 'f4c19a72d830'
down_revision = 'e8b2c6d91f40'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('users')}
    if 'permissions' not in columns:
        op.add_column('users', sa.Column('permissions', sa.Text(), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('users')}
    if 'permissions' in columns:
        op.drop_column('users', 'permissions')
