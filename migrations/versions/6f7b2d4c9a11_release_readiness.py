"""commercial release readiness

Revision ID: 6f7b2d4c9a11
Revises: 5d2a8c91e740
"""
from alembic import op
import sqlalchemy as sa

revision = '6f7b2d4c9a11'
down_revision = '5d2a8c91e740'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('users')}
    if 'email_verified_at' not in columns:
        op.add_column('users', sa.Column('email_verified_at', sa.DateTime(), nullable=True))
        # Existing accounts are trusted as grandfathered accounts. New public
        # registrations are created unverified by the application.
        op.execute(sa.text('UPDATE users SET email_verified_at = NOW() WHERE email_verified_at IS NULL'))
        op.create_index('ix_users_email_verified_at', 'users', ['email_verified_at'])
    if 'email_verification_sent_at' not in columns:
        op.add_column('users', sa.Column('email_verification_sent_at', sa.DateTime(), nullable=True))
    if 'terms_accepted_at' not in columns:
        op.add_column('users', sa.Column('terms_accepted_at', sa.DateTime(), nullable=True))
    if 'legal_version' not in columns:
        op.add_column('users', sa.Column('legal_version', sa.String(40), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('users')}
    if 'legal_version' in columns:
        op.drop_column('users', 'legal_version')
    if 'terms_accepted_at' in columns:
        op.drop_column('users', 'terms_accepted_at')
    if 'email_verification_sent_at' in columns:
        op.drop_column('users', 'email_verification_sent_at')
    if 'email_verified_at' in columns:
        try:
            op.drop_index('ix_users_email_verified_at', table_name='users')
        except Exception:
            pass
        op.drop_column('users', 'email_verified_at')
