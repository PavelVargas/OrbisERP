"""Constrain price-rule percentages to the supported range.

Revision ID: d4f25b8a3c71
Revises: c8e4a1f7b602
"""
from alembic import op

revision = "d4f25b8a3c71"
down_revision = "c8e4a1f7b602"
branch_labels = None
depends_on = None


def upgrade():
    # Normalize invalid historical rows so the new invariant can be installed
    # without breaking an existing production upgrade.
    op.execute("UPDATE price_list_rules SET percent = 0 WHERE percent < 0")
    op.execute("UPDATE price_list_rules SET percent = 100 WHERE percent > 100")
    op.create_check_constraint(
        "ck_price_rule_percent_range",
        "price_list_rules",
        "percent IS NULL OR (percent >= 0 AND percent <= 100)",
    )


def downgrade():
    op.drop_constraint(
        "ck_price_rule_percent_range",
        "price_list_rules",
        type_="check",
    )
