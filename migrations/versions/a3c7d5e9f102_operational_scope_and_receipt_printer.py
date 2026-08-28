"""operational scope and receipt printer

Revision ID: a3c7d5e9f102
Revises: f9b2d8e4a713
"""
from alembic import op
import sqlalchemy as sa

revision = 'a3c7d5e9f102'
down_revision = 'f9b2d8e4a713'
branch_labels = None
depends_on = None


def _columns(table):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _checks(table):
    return {row.get('name') for row in sa.inspect(op.get_bind()).get_check_constraints(table)}


def _indexes(table):
    return {row.get('name') for row in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade():
    if 'receipt_printer_mode' not in _columns('company_retail_settings'):
        op.add_column('company_retail_settings', sa.Column('receipt_printer_mode', sa.String(length=20), nullable=False, server_default='BROWSER'))
    if 'receipt_printer_name' not in _columns('company_retail_settings'):
        op.add_column('company_retail_settings', sa.Column('receipt_printer_name', sa.String(length=160), nullable=True))
    if 'receipt_auto_print' not in _columns('company_retail_settings'):
        op.add_column('company_retail_settings', sa.Column('receipt_auto_print', sa.Boolean(), nullable=False, server_default=sa.false()))

    checks = _checks('company_retail_settings')
    if 'ck_retail_receipt_width' in checks:
        op.drop_constraint('ck_retail_receipt_width', 'company_retail_settings', type_='check')
    op.create_check_constraint('ck_retail_receipt_width', 'company_retail_settings', 'default_receipt_width BETWEEN 40 AND 112')
    if 'ck_retail_printer_mode' not in checks:
        op.create_check_constraint('ck_retail_printer_mode', 'company_retail_settings', "receipt_printer_mode IN ('BROWSER','WEBUSB','ELECTRON')")

    terminal_checks = _checks('pos_terminals')
    if 'ck_terminal_receipt_width' in terminal_checks:
        op.drop_constraint('ck_terminal_receipt_width', 'pos_terminals', type_='check')
    op.create_check_constraint('ck_terminal_receipt_width', 'pos_terminals', 'receipt_width BETWEEN 40 AND 112')

    if 'branch_id' not in _columns('cash_sessions'):
        op.add_column('cash_sessions', sa.Column('branch_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_cash_sessions_branch_id', 'cash_sessions', 'branches', ['branch_id'], ['id'])
        op.create_index('ix_cash_sessions_branch_id', 'cash_sessions', ['branch_id'])
        op.execute(sa.text("""
            UPDATE cash_sessions cs
               SET branch_id = COALESCE(
                   (SELECT pt.branch_id FROM pos_terminals pt WHERE pt.id = cs.terminal_id),
                   (SELECT u.branch_id FROM users u WHERE u.id = cs.user_id)
               )
             WHERE cs.branch_id IS NULL
        """))
    indexes = _indexes('cash_sessions')
    if 'uq_cash_sessions_open_user' in indexes:
        op.drop_index('uq_cash_sessions_open_user', table_name='cash_sessions')
    if 'uq_cash_sessions_open_user_branch' not in _indexes('cash_sessions'):
        op.create_index(
            'uq_cash_sessions_open_user_branch', 'cash_sessions',
            ['company_id', 'user_id', 'branch_id'], unique=True,
            postgresql_where=sa.text("status = 'OPEN'"),
        )

    if 'branch_id' not in _columns('cash_closings'):
        op.add_column('cash_closings', sa.Column('branch_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_cash_closings_branch_id', 'cash_closings', 'branches', ['branch_id'], ['id'])
        op.create_index('ix_cash_closings_branch_id', 'cash_closings', ['branch_id'])
    if 'terminal_id' not in _columns('cash_closings'):
        op.add_column('cash_closings', sa.Column('terminal_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_cash_closings_terminal_id', 'cash_closings', 'pos_terminals', ['terminal_id'], ['id'])
        op.create_index('ix_cash_closings_terminal_id', 'cash_closings', ['terminal_id'])
    op.execute(sa.text("""
        UPDATE cash_closings cc
           SET branch_id = u.branch_id
          FROM users u
         WHERE u.id = cc.user_id AND cc.branch_id IS NULL
    """))

    if 'branch_id' not in _columns('expenses'):
        op.add_column('expenses', sa.Column('branch_id', sa.Integer(), nullable=True))
        op.create_foreign_key('fk_expenses_branch_id', 'expenses', 'branches', ['branch_id'], ['id'])
        op.create_index('ix_expenses_branch_id', 'expenses', ['branch_id'])
        op.execute(sa.text("""
            UPDATE expenses e
               SET branch_id = u.branch_id
              FROM users u
             WHERE u.id = e.user_id AND e.branch_id IS NULL
        """))


def downgrade():
    indexes = _indexes('cash_sessions')
    if 'uq_cash_sessions_open_user_branch' in indexes:
        op.drop_index('uq_cash_sessions_open_user_branch', table_name='cash_sessions')
    if 'uq_cash_sessions_open_user' not in _indexes('cash_sessions'):
        op.create_index(
            'uq_cash_sessions_open_user', 'cash_sessions', ['company_id', 'user_id'],
            unique=True, postgresql_where=sa.text("status = 'OPEN'"),
        )

    for table, column, fk, index in (
        ('expenses', 'branch_id', 'fk_expenses_branch_id', 'ix_expenses_branch_id'),
        ('cash_closings', 'terminal_id', 'fk_cash_closings_terminal_id', 'ix_cash_closings_terminal_id'),
        ('cash_closings', 'branch_id', 'fk_cash_closings_branch_id', 'ix_cash_closings_branch_id'),
        ('cash_sessions', 'branch_id', 'fk_cash_sessions_branch_id', 'ix_cash_sessions_branch_id'),
    ):
        if column in _columns(table):
            if index in _indexes(table):
                op.drop_index(index, table_name=table)
            op.drop_constraint(fk, table, type_='foreignkey')
            op.drop_column(table, column)

    checks = _checks('pos_terminals')
    if 'ck_terminal_receipt_width' in checks:
        op.drop_constraint('ck_terminal_receipt_width', 'pos_terminals', type_='check')
    op.create_check_constraint('ck_terminal_receipt_width', 'pos_terminals', 'receipt_width IN (58,80)')

    checks = _checks('company_retail_settings')
    if 'ck_retail_printer_mode' in checks:
        op.drop_constraint('ck_retail_printer_mode', 'company_retail_settings', type_='check')
    if 'ck_retail_receipt_width' in checks:
        op.drop_constraint('ck_retail_receipt_width', 'company_retail_settings', type_='check')
    op.create_check_constraint('ck_retail_receipt_width', 'company_retail_settings', 'default_receipt_width IN (58,80)')
    for column in ('receipt_auto_print', 'receipt_printer_name', 'receipt_printer_mode'):
        if column in _columns('company_retail_settings'):
            op.drop_column('company_retail_settings', column)
