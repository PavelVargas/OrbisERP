"""make product warranties an always-on retail baseline

Revision ID: e3f8b61c2a74
Revises: d7a1c4e9b206
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f8b61c2a74'
down_revision = 'd7a1c4e9b206'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if 'products' in tables:
        columns = {c['name'] for c in inspector.get_columns('products')}
        if 'warranty_days' in columns:
            bind.execute(sa.text("UPDATE products SET warranty_days = 30 WHERE warranty_days IS NULL OR warranty_days < 1"))
            checks = {row.get('name') for row in inspector.get_check_constraints('products')}
            if 'ck_products_warranty_days' in checks:
                op.drop_constraint('ck_products_warranty_days', 'products', type_='check')
            op.create_check_constraint('ck_products_warranty_days', 'products', 'warranty_days >= 1')
            op.alter_column('products', 'warranty_days', server_default=sa.text('30'), existing_type=sa.Integer(), existing_nullable=False)
    if 'company_retail_settings' in tables:
        columns = {c['name'] for c in inspector.get_columns('company_retail_settings')}
        if 'enable_warranties' in columns:
            bind.execute(sa.text("UPDATE company_retail_settings SET enable_warranties = TRUE WHERE enable_warranties IS DISTINCT FROM TRUE"))
            op.alter_column('company_retail_settings', 'enable_warranties', server_default=sa.text('TRUE'), existing_type=sa.Boolean(), existing_nullable=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if 'products' in tables and 'warranty_days' in {c['name'] for c in inspector.get_columns('products')}:
        checks = {row.get('name') for row in inspector.get_check_constraints('products')}
        if 'ck_products_warranty_days' in checks:
            op.drop_constraint('ck_products_warranty_days', 'products', type_='check')
        op.create_check_constraint('ck_products_warranty_days', 'products', 'warranty_days >= 0')
        op.alter_column('products', 'warranty_days', server_default=None, existing_type=sa.Integer(), existing_nullable=False)
    if 'company_retail_settings' in tables and 'enable_warranties' in {c['name'] for c in inspector.get_columns('company_retail_settings')}:
        op.alter_column('company_retail_settings', 'enable_warranties', server_default=None, existing_type=sa.Boolean(), existing_nullable=False)
