"""Store currency exchange rate as exact numeric.

Revision ID: c8e4a1f7b602
Revises: f5a9c2d8e641
"""
from alembic import op
import sqlalchemy as sa

revision = "c8e4a1f7b602"
down_revision = "f5a9c2d8e641"
branch_labels = None
depends_on = None


def upgrade():
    # Clean special/out-of-range floating-point values before the exact cast.
    # This avoids an upgrade failure when a legacy row contains Infinity/NaN.
    op.execute(
        "UPDATE exchange_rates SET rate = 1 "
        "WHERE rate::text IN ('NaN', 'Infinity', '-Infinity') "
        "OR rate <= 0 OR rate > 9999999999.99999999"
    )
    op.alter_column(
        "exchange_rates",
        "rate",
        existing_type=sa.Float(),
        type_=sa.Numeric(18, 8),
        existing_nullable=False,
        postgresql_using="rate::numeric(18,8)",
    )
    op.create_check_constraint(
        "ck_exchange_rates_rate_range",
        "exchange_rates",
        "rate > 0 AND rate <= 9999999999.99999999",
    )


def downgrade():
    op.drop_constraint(
        "ck_exchange_rates_rate_range",
        "exchange_rates",
        type_="check",
    )
    op.alter_column(
        "exchange_rates",
        "rate",
        existing_type=sa.Numeric(18, 8),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="rate::double precision",
    )
