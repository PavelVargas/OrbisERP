"""commercial operations

Revision ID: b7e4a0d32591
Revises: a6d3f9c21480
"""
from alembic import op
import sqlalchemy as sa


revision = 'b7e4a0d32591'
down_revision = 'a6d3f9c21480'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    company_columns = {column['name'] for column in inspector.get_columns('companies')}
    additions = {
        'billing_provider': sa.Column('billing_provider', sa.String(40)),
        'billing_customer_id': sa.Column('billing_customer_id', sa.String(120)),
        'billing_subscription_id': sa.Column('billing_subscription_id', sa.String(120)),
        'cancel_at_period_end': sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default=sa.false()),
        'onboarding_completed': sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default=sa.false()),
    }
    for name, column in additions.items():
        if name not in company_columns:
            op.add_column('companies', column)
    tables = set(inspector.get_table_names())
    if 'billing_invoices' not in tables:
        op.create_table(
            'billing_invoices',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('external_id', sa.String(120), nullable=False, unique=True),
            sa.Column('provider', sa.String(40), nullable=False),
            sa.Column('status', sa.String(30), nullable=False),
            sa.Column('plan_name', sa.String(20), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(3), nullable=False),
            sa.Column('period_start', sa.DateTime()), sa.Column('period_end', sa.DateTime()),
            sa.Column('paid_at', sa.DateTime()), sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_billing_invoices_company_id', 'billing_invoices', ['company_id'])
    if 'subscription_events' not in tables:
        op.create_table(
            'subscription_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('event_id', sa.String(150), nullable=False, unique=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id')),
            sa.Column('provider', sa.String(40), nullable=False),
            sa.Column('event_type', sa.String(80), nullable=False),
            sa.Column('payload_hash', sa.String(64), nullable=False),
            sa.Column('processed', sa.Boolean(), nullable=False),
            sa.Column('error', sa.Text()), sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_subscription_events_company_id', 'subscription_events', ['company_id'])


def downgrade():
    op.drop_table('subscription_events')
    op.drop_table('billing_invoices')
    for column in ('onboarding_completed', 'cancel_at_period_end', 'billing_subscription_id', 'billing_customer_id', 'billing_provider'):
        op.drop_column('companies', column)
