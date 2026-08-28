"""add category description

Revision ID: f9b2d8e4a713
Revises: e91b7c4a206f
"""
from alembic import op
import sqlalchemy as sa

revision = 'f9b2d8e4a713'
down_revision = 'e91b7c4a206f'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('categories')}
    if 'description' not in columns:
        op.add_column('categories', sa.Column('description', sa.Text(), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('categories')}
    if 'description' in columns:
        op.drop_column('categories', 'description')
