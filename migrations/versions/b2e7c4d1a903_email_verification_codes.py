"""four-digit email verification codes

Revision ID: b2e7c4d1a903
Revises: 9f4a2c7e1b33
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2e7c4d1a903'
down_revision = '9f4a2c7e1b33'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c['name'] for c in sa.inspect(bind).get_columns('users')}
    if 'email_verification_code_hash' not in columns:
        op.add_column('users', sa.Column('email_verification_code_hash', sa.String(length=64), nullable=True))
    if 'email_verification_code_expires_at' not in columns:
        op.add_column('users', sa.Column('email_verification_code_expires_at', sa.DateTime(), nullable=True))
    if 'email_verification_attempts' not in columns:
        op.add_column('users', sa.Column('email_verification_attempts', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    bind = op.get_bind()
    columns = {c['name'] for c in sa.inspect(bind).get_columns('users')}
    if 'email_verification_attempts' in columns:
        op.drop_column('users', 'email_verification_attempts')
    if 'email_verification_code_expires_at' in columns:
        op.drop_column('users', 'email_verification_code_expires_at')
    if 'email_verification_code_hash' in columns:
        op.drop_column('users', 'email_verification_code_hash')
