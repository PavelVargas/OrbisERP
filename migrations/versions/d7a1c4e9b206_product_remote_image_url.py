"""add optional remote product image URL

Revision ID: d7a1c4e9b206
Revises: b2e7c4d1a903
"""
from alembic import op
import sqlalchemy as sa

revision = 'd7a1c4e9b206'
down_revision = 'b2e7c4d1a903'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'products' not in inspector.get_table_names():
        return
    columns = {c['name'] for c in inspector.get_columns('products')}
    if 'image_url' not in columns:
        op.add_column('products', sa.Column('image_url', sa.String(length=2048), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'products' not in inspector.get_table_names():
        return
    columns = {c['name'] for c in inspector.get_columns('products')}
    if 'image_url' in columns:
        op.drop_column('products', 'image_url')
