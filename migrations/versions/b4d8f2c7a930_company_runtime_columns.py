"""company runtime columns

Revision ID: b4d8f2c7a930
Revises: a3c7d5e9f102
Create Date: 2026-08-29

Keeps the companies table aligned with models/company/company.py for clean
PostgreSQL installations used by CI and new deployments.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b4d8f2c7a930'
down_revision = 'a3c7d5e9f102'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    company_columns = {column['name'] for column in inspector.get_columns('companies')}

    if 'is_readonly' not in company_columns:
        op.add_column(
            'companies',
            sa.Column('is_readonly', sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if 'storage_limit' not in company_columns:
        op.add_column(
            'companies',
            sa.Column('storage_limit', sa.BigInteger(), nullable=True, server_default='524288000'),
        )

    if 'current_storage_usage' not in company_columns:
        op.add_column(
            'companies',
            sa.Column('current_storage_usage', sa.BigInteger(), nullable=True, server_default='0'),
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    company_columns = {column['name'] for column in inspector.get_columns('companies')}

    for name in ('current_storage_usage', 'storage_limit', 'is_readonly'):
        if name in company_columns:
            op.drop_column('companies', name)
