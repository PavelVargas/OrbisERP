"""production hardening

Revision ID: 1f9c3a7e5b20
Revises: c8f2a91d640e
"""
from alembic import op
import sqlalchemy as sa


revision = '1f9c3a7e5b20'
down_revision = 'c8f2a91d640e'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if 'security_attempts' not in tables:
        op.create_table(
            'security_attempts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('scope', sa.String(80), nullable=False),
            sa.Column('subject_hash', sa.String(64), nullable=False),
            sa.Column('attempted_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_security_attempts_scope', 'security_attempts', ['scope'])
        op.create_index('ix_security_attempts_subject_hash', 'security_attempts', ['subject_hash'])
        op.create_index('ix_security_attempts_attempted_at', 'security_attempts', ['attempted_at'])

    exchange_constraints = {item.get('name') for item in inspector.get_unique_constraints('exchange_rates')}
    if 'uq_exchange_rate_company_currency' not in exchange_constraints:
        duplicates = sa.text('''
            DELETE FROM exchange_rates a USING exchange_rates b
            WHERE a.id > b.id
              AND a.company_id = b.company_id
              AND upper(a.currency_code) = upper(b.currency_code)
        ''')
        op.get_bind().execute(duplicates)
        op.create_unique_constraint(
            'uq_exchange_rate_company_currency', 'exchange_rates', ['company_id', 'currency_code']
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if 'uq_exchange_rate_company_currency' in {item.get('name') for item in inspector.get_unique_constraints('exchange_rates')}:
        op.drop_constraint('uq_exchange_rate_company_currency', 'exchange_rates', type_='unique')
    if 'security_attempts' in set(inspector.get_table_names()):
        op.drop_table('security_attempts')
