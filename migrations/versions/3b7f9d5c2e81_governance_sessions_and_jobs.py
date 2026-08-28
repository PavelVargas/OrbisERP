"""governance sessions and jobs

Revision ID: 3b7f9d5c2e81
Revises: 2a6e8c4b1d70
"""
from alembic import op
import sqlalchemy as sa


revision = '3b7f9d5c2e81'
down_revision = '2a6e8c4b1d70'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    user_columns = {column['name'] for column in inspector.get_columns('users')}
    if 'totp_recovery_codes' not in user_columns:
        op.add_column('users', sa.Column('totp_recovery_codes', sa.Text(), nullable=True))

    audit_columns = {column['name'] for column in inspector.get_columns('audit_logs')}
    additions = {
        'request_id': sa.Column('request_id', sa.String(64), nullable=True),
        'endpoint': sa.Column('endpoint', sa.String(150), nullable=True),
        'entity_type': sa.Column('entity_type', sa.String(80), nullable=True),
        'entity_id': sa.Column('entity_id', sa.String(80), nullable=True),
    }
    for name, column in additions.items():
        if name not in audit_columns:
            op.add_column('audit_logs', column)
    inspector = sa.inspect(bind)
    audit_indexes = {item['name'] for item in inspector.get_indexes('audit_logs')}
    for name in ('request_id', 'endpoint', 'entity_type'):
        index_name = f'ix_audit_logs_{name}'
        if index_name not in audit_indexes:
            op.create_index(index_name, 'audit_logs', [name])

    if 'user_sessions' not in tables:
        op.create_table(
            'user_sessions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('session_hash', sa.String(64), nullable=False, unique=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=True),
            sa.Column('ip_address', sa.String(50)), sa.Column('user_agent', sa.String(255)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('last_seen_at', sa.DateTime(), nullable=False),
            sa.Column('revoked_at', sa.DateTime()), sa.Column('revoke_reason', sa.String(120)),
        )
        for column in ('session_hash', 'user_id', 'company_id', 'last_seen_at', 'revoked_at'):
            op.create_index(f'ix_user_sessions_{column}', 'user_sessions', [column])

    if 'operation_jobs' not in tables:
        op.create_table(
            'operation_jobs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('job_type', sa.String(50), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
            sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('processed_rows', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('error_summary', sa.Text()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('started_at', sa.DateTime()), sa.Column('finished_at', sa.DateTime()),
            sa.CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED')", name='ck_operation_jobs_status'),
            sa.CheckConstraint('progress >= 0 AND progress <= 100', name='ck_operation_jobs_progress'),
            sa.CheckConstraint('total_rows >= 0 AND processed_rows >= 0 AND error_count >= 0', name='ck_operation_jobs_counts'),
        )
        for column in ('company_id', 'user_id', 'job_type', 'status', 'created_at'):
            op.create_index(f'ix_operation_jobs_{column}', 'operation_jobs', [column])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in ('operation_jobs', 'user_sessions'):
        if table in tables:
            op.drop_table(table)
    audit_columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('audit_logs')}
    for name in ('entity_id', 'entity_type', 'endpoint', 'request_id'):
        if name in audit_columns:
            op.drop_column('audit_logs', name)
    user_columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('users')}
    if 'totp_recovery_codes' in user_columns:
        op.drop_column('users', 'totp_recovery_codes')
