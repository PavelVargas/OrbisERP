"""add optional product image

Revision ID: c31e8d7a42b0
Revises: 8b4d1f23a910
"""
from alembic import op
import sqlalchemy as sa

revision = 'c31e8d7a42b0'
down_revision = '8b4d1f23a910'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('products')}
    if 'image_path' not in columns:
        op.add_column('products', sa.Column('image_path', sa.String(length=255), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('products')}
    if 'image_path' in columns:
        op.drop_column('products', 'image_path')
