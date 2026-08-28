"""workspace experience upgrade

Revision ID: 5d2a8c91e740
Revises: 4c9e2f7a6b10
"""
from alembic import op
import sqlalchemy as sa


revision = '5d2a8c91e740'
down_revision = '4c9e2f7a6b10'
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return {column['name'] for column in inspector.get_columns(table)}


def _constraints(inspector, table):
    names = {item.get('name') for item in inspector.get_unique_constraints(table)}
    names.update(item.get('name') for item in inspector.get_check_constraints(table))
    return names


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    user_cols = _columns(inspector, 'users')
    if 'avatar_path' not in user_cols:
        op.add_column('users', sa.Column('avatar_path', sa.String(255), nullable=True))

    if 'document_folders' not in tables:
        op.create_table(
            'document_folders',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('parent_id', sa.Integer(), sa.ForeignKey('document_folders.id'), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_document_folders_company_id', 'document_folders', ['company_id'])
        op.create_index('ix_document_folders_parent_id', 'document_folders', ['parent_id'])
        op.create_index('ix_document_folders_created_at', 'document_folders', ['created_at'])

    inspector = sa.inspect(bind)
    doc_cols = _columns(inspector, 'company_documents')
    if 'folder_id' not in doc_cols:
        op.add_column('company_documents', sa.Column('folder_id', sa.Integer(), sa.ForeignKey('document_folders.id'), nullable=True))
        op.create_index('ix_company_documents_folder_id', 'company_documents', ['folder_id'])
    if 'updated_at' not in doc_cols:
        op.add_column('company_documents', sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.func.now()))
        op.execute(sa.text('UPDATE company_documents SET updated_at = COALESCE(created_at, NOW()) WHERE updated_at IS NULL'))
        op.alter_column('company_documents', 'updated_at', nullable=False)

    inspector = sa.inspect(bind)
    rule_cols = _columns(inspector, 'notification_rules')
    additions = (
        ('name', sa.Column('name', sa.String(120), nullable=True)),
        ('custom_source', sa.Column('custom_source', sa.String(30), nullable=True)),
        ('operator', sa.Column('operator', sa.String(8), nullable=True)),
        ('lookback_days', sa.Column('lookback_days', sa.Integer(), nullable=False, server_default='30')),
        ('message', sa.Column('message', sa.String(255), nullable=True)),
        ('link', sa.Column('link', sa.String(255), nullable=True)),
        ('target_user_id', sa.Column('target_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True)),
    )
    for name, column in additions:
        if name not in rule_cols:
            op.add_column('notification_rules', column)
    if 'target_user_id' not in rule_cols:
        op.create_index('ix_notification_rules_target_user_id', 'notification_rules', ['target_user_id'])

    constraints = _constraints(sa.inspect(bind), 'notification_rules')
    if 'uq_notification_rules_company_type' in constraints:
        op.drop_constraint('uq_notification_rules_company_type', 'notification_rules', type_='unique')
    if 'ck_notification_rules_type' in constraints:
        op.drop_constraint('ck_notification_rules_type', 'notification_rules', type_='check')
    constraints = _constraints(sa.inspect(bind), 'notification_rules')
    if 'ck_notification_rules_operator' not in constraints:
        op.create_check_constraint(
            'ck_notification_rules_operator', 'notification_rules',
            "operator IS NULL OR operator IN ('LT','LTE','EQ','GTE','GT')",
        )
    if 'ck_notification_rules_lookback_nonnegative' not in constraints:
        op.create_check_constraint('ck_notification_rules_lookback_nonnegative', 'notification_rules', 'lookback_days >= 0')

    op.execute(sa.text("""
        UPDATE notification_rules
        SET name = CASE rule_type
            WHEN 'STOCK_BELOW_MIN' THEN 'Stock bajo'
            WHEN 'RECEIVABLE_OVERDUE' THEN 'Cobros vencidos'
            WHEN 'PAYABLE_DUE' THEN 'Pagos próximos'
            ELSE COALESCE(name, rule_type)
        END
        WHERE name IS NULL OR name = ''
    """))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'notification_rules' in set(inspector.get_table_names()):
        constraints = _constraints(inspector, 'notification_rules')
        if 'ck_notification_rules_operator' in constraints:
            op.drop_constraint('ck_notification_rules_operator', 'notification_rules', type_='check')
        if 'ck_notification_rules_lookback_nonnegative' in constraints:
            op.drop_constraint('ck_notification_rules_lookback_nonnegative', 'notification_rules', type_='check')
        op.execute(sa.text("DELETE FROM notification_rules WHERE rule_type NOT IN ('STOCK_BELOW_MIN','RECEIVABLE_OVERDUE','PAYABLE_DUE')"))
        op.execute(sa.text("DELETE FROM notification_rules a USING notification_rules b WHERE a.company_id=b.company_id AND a.rule_type=b.rule_type AND a.id>b.id"))
        op.create_unique_constraint('uq_notification_rules_company_type', 'notification_rules', ['company_id', 'rule_type'])
        op.create_check_constraint(
            'ck_notification_rules_type', 'notification_rules',
            "rule_type IN ('STOCK_BELOW_MIN','RECEIVABLE_OVERDUE','PAYABLE_DUE')",
        )
        cols = _columns(sa.inspect(bind), 'notification_rules')
        for column in ('target_user_id', 'link', 'message', 'lookback_days', 'operator', 'custom_source', 'name'):
            if column in cols:
                if column == 'target_user_id':
                    try:
                        op.drop_index('ix_notification_rules_target_user_id', table_name='notification_rules')
                    except Exception:
                        pass
                op.drop_column('notification_rules', column)

    if 'company_documents' in set(sa.inspect(bind).get_table_names()):
        cols = _columns(sa.inspect(bind), 'company_documents')
        if 'folder_id' in cols:
            try:
                op.drop_index('ix_company_documents_folder_id', table_name='company_documents')
            except Exception:
                pass
            op.drop_column('company_documents', 'folder_id')
        if 'updated_at' in cols:
            op.drop_column('company_documents', 'updated_at')

    if 'document_folders' in set(sa.inspect(bind).get_table_names()):
        op.drop_table('document_folders')

    if 'avatar_path' in _columns(sa.inspect(bind), 'users'):
        op.drop_column('users', 'avatar_path')
