"""preserve four decimal places for loyalty balances

Revision ID: e91b7c4a206f
Revises: d4f25b8a3c71
Create Date: 2026-08-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'e91b7c4a206f'
down_revision = 'd4f25b8a3c71'
branch_labels = None
depends_on = None


def upgrade():
    # Normalize legacy special values before changing precision. PostgreSQL
    # numeric accepts NaN/Infinity, but loyalty balances must always be finite.
    op.execute(
        "UPDATE clients SET loyalty_points = 0 "
        "WHERE loyalty_points::text IN ('NaN', 'Infinity', '-Infinity') "
        "OR loyalty_points < 0 OR loyalty_points > 9999999999.9999"
    )
    op.execute(
        "UPDATE loyalty_transactions SET points = 0 "
        "WHERE points::text IN ('NaN', 'Infinity', '-Infinity') "
        "OR points < -9999999999.9999 OR points > 9999999999.9999"
    )
    op.execute(
        "UPDATE loyalty_transactions SET balance_after = 0 "
        "WHERE balance_after::text IN ('NaN', 'Infinity', '-Infinity') "
        "OR balance_after < 0 OR balance_after > 9999999999.9999"
    )
    op.alter_column('clients', 'loyalty_points',
                    existing_type=sa.Numeric(precision=14, scale=3),
                    type_=sa.Numeric(precision=14, scale=4),
                    existing_nullable=False)
    op.alter_column('loyalty_transactions', 'points',
                    existing_type=sa.Numeric(precision=14, scale=3),
                    type_=sa.Numeric(precision=14, scale=4),
                    existing_nullable=False)
    op.alter_column('loyalty_transactions', 'balance_after',
                    existing_type=sa.Numeric(precision=14, scale=3),
                    type_=sa.Numeric(precision=14, scale=4),
                    existing_nullable=False)
    op.create_check_constraint(
        'ck_clients_loyalty_points_range', 'clients',
        'loyalty_points >= 0 AND loyalty_points <= 9999999999.9999',
    )
    op.create_check_constraint(
        'ck_loyalty_transaction_points_range', 'loyalty_transactions',
        'points >= -9999999999.9999 AND points <= 9999999999.9999 '
        'AND balance_after >= 0 AND balance_after <= 9999999999.9999',
    )


def downgrade():
    op.drop_constraint('ck_loyalty_transaction_points_range', 'loyalty_transactions', type_='check')
    op.drop_constraint('ck_clients_loyalty_points_range', 'clients', type_='check')
    op.execute('UPDATE clients SET loyalty_points = ROUND(loyalty_points, 3)')
    op.execute('UPDATE loyalty_transactions SET points = ROUND(points, 3), balance_after = ROUND(balance_after, 3)')
    op.alter_column('loyalty_transactions', 'balance_after',
                    existing_type=sa.Numeric(precision=14, scale=4),
                    type_=sa.Numeric(precision=14, scale=3),
                    existing_nullable=False)
    op.alter_column('loyalty_transactions', 'points',
                    existing_type=sa.Numeric(precision=14, scale=4),
                    type_=sa.Numeric(precision=14, scale=3),
                    existing_nullable=False)
    op.alter_column('clients', 'loyalty_points',
                    existing_type=sa.Numeric(precision=14, scale=4),
                    type_=sa.Numeric(precision=14, scale=3),
                    existing_nullable=False)
