"""security and tenant constraints

Revision ID: 8b4d1f23a910
Revises: 77f09e7954f3
"""
from alembic import op
import sqlalchemy as sa

revision = '8b4d1f23a910'
down_revision = '77f09e7954f3'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('users', 'password', type_=sa.String(length=255), existing_type=sa.String(length=150))
    op.drop_constraint('products_sku_key', 'products', type_='unique')
    op.create_unique_constraint('uq_products_company_sku', 'products', ['company_id', 'sku'])


def downgrade():
    op.drop_constraint('uq_products_company_sku', 'products', type_='unique')
    op.create_unique_constraint('products_sku_key', 'products', ['sku'])
    op.alter_column('users', 'password', type_=sa.String(length=150), existing_type=sa.String(length=255))
