"""sale cash tender and change

Revision ID: c6e1a4f8b207
Revises: b4d8f2c7a930
Create Date: 2026-08-29

Persists the physical cash tendered by the customer and the change returned by
POS cashiers.  ``sales.amount_paid`` continues to represent the amount applied
to the sale, so cash reconciliation and accounting semantics stay unchanged.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c6e1a4f8b207'
down_revision = 'b4d8f2c7a930'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('sales')}

    if 'cash_received' not in columns:
        op.add_column('sales', sa.Column('cash_received', sa.Numeric(12, 2), nullable=True))
    if 'cash_change' not in columns:
        op.add_column(
            'sales',
            sa.Column('cash_change', sa.Numeric(12, 2), nullable=False, server_default='0'),
        )

    constraints = {item['name'] for item in inspector.get_check_constraints('sales') if item.get('name')}
    if 'ck_sales_cash_received_nonnegative' not in constraints:
        op.create_check_constraint(
            'ck_sales_cash_received_nonnegative', 'sales', 'cash_received IS NULL OR cash_received >= 0'
        )
    if 'ck_sales_cash_change_nonnegative' not in constraints:
        op.create_check_constraint('ck_sales_cash_change_nonnegative', 'sales', 'cash_change >= 0')


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('sales')}
    constraints = {item['name'] for item in inspector.get_check_constraints('sales') if item.get('name')}
    if 'ck_sales_cash_change_nonnegative' in constraints:
        op.drop_constraint('ck_sales_cash_change_nonnegative', 'sales', type_='check')
    if 'ck_sales_cash_received_nonnegative' in constraints:
        op.drop_constraint('ck_sales_cash_received_nonnegative', 'sales', type_='check')
    if 'cash_change' in columns:
        op.drop_column('sales', 'cash_change')
    if 'cash_received' in columns:
        op.drop_column('sales', 'cash_received')
