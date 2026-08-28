"""productivity suite

Revision ID: 4c9e2f7a6b10
Revises: 3b7f9d5c2e81
"""
from alembic import op
import sqlalchemy as sa


revision = '4c9e2f7a6b10'
down_revision = '3b7f9d5c2e81'
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return {column['name'] for column in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if 'sales_taxes' not in tables:
        op.create_table(
            'sales_taxes',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('name', sa.String(80), nullable=False),
            sa.Column('rate', sa.Numeric(5, 2), nullable=False, server_default='0'),
            sa.Column('price_included', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('company_id', 'name', name='uq_sales_taxes_company_name'),
            sa.CheckConstraint('rate >= 0 AND rate <= 100', name='ck_sales_taxes_rate_range'),
        )
        op.create_index('ix_sales_taxes_company_id', 'sales_taxes', ['company_id'])
        op.create_index(
            'uq_sales_taxes_default_company', 'sales_taxes', ['company_id'], unique=True,
            postgresql_where=sa.text('is_default = TRUE'), sqlite_where=sa.text('is_default = 1'),
        )

    if 'promotions' not in tables:
        op.create_table(
            'promotions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('code', sa.String(40), nullable=False),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('discount_type', sa.String(20), nullable=False, server_default='PERCENT'),
            sa.Column('value', sa.Numeric(12, 2), nullable=False),
            sa.Column('min_total', sa.Numeric(12, 2), nullable=False, server_default='0'),
            sa.Column('starts_at', sa.DateTime()), sa.Column('ends_at', sa.DateTime()),
            sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('company_id', 'code', name='uq_promotions_company_code'),
            sa.CheckConstraint("discount_type IN ('PERCENT','FIXED')", name='ck_promotions_discount_type'),
            sa.CheckConstraint('value > 0', name='ck_promotions_value_positive'),
            sa.CheckConstraint('min_total >= 0', name='ck_promotions_min_total_nonnegative'),
            sa.CheckConstraint("discount_type != 'PERCENT' OR value <= 100", name='ck_promotions_percent_range'),
            sa.CheckConstraint(
                'starts_at IS NULL OR ends_at IS NULL OR ends_at >= starts_at',
                name='ck_promotions_date_range',
            ),
        )
        op.create_index('ix_promotions_company_id', 'promotions', ['company_id'])
        op.create_index('ix_promotions_code', 'promotions', ['code'])

    if 'cash_sessions' not in tables:
        op.create_table(
            'cash_sessions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='OPEN'),
            sa.Column('opening_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
            sa.Column('expected_amount', sa.Numeric(12, 2)),
            sa.Column('counted_amount', sa.Numeric(12, 2)),
            sa.Column('difference', sa.Numeric(12, 2)),
            sa.Column('notes', sa.Text()),
            sa.Column('opened_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('closed_at', sa.DateTime()),
            sa.CheckConstraint("status IN ('OPEN','CLOSED')", name='ck_cash_sessions_status'),
            sa.CheckConstraint('opening_amount >= 0', name='ck_cash_sessions_opening_nonnegative'),
            sa.CheckConstraint('counted_amount IS NULL OR counted_amount >= 0', name='ck_cash_sessions_counted_nonnegative'),
        )
        for col in ('company_id', 'user_id', 'status', 'opened_at'):
            op.create_index(f'ix_cash_sessions_{col}', 'cash_sessions', [col])
        op.create_index('uq_cash_sessions_open_user', 'cash_sessions', ['company_id', 'user_id'], unique=True,
                        postgresql_where=sa.text("status = 'OPEN'"), sqlite_where=sa.text("status = 'OPEN'"))

    if 'company_documents' not in tables:
        op.create_table(
            'company_documents',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('entity_type', sa.String(40), nullable=False, server_default='COMPANY'),
            sa.Column('entity_id', sa.Integer()),
            sa.Column('display_name', sa.String(180), nullable=False),
            sa.Column('stored_name', sa.String(255), nullable=False, unique=True),
            sa.Column('mime_type', sa.String(100)),
            sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "entity_type IN ('COMPANY','PRODUCT','CLIENT','SUPPLIER','SALE','PURCHASE','EXPENSE')",
                name='ck_company_documents_entity_type',
            ),
            sa.CheckConstraint('size_bytes >= 0', name='ck_company_documents_size_nonnegative'),
        )
        for col in ('company_id', 'entity_type', 'entity_id', 'created_at'):
            op.create_index(f'ix_company_documents_{col}', 'company_documents', [col])

    if 'notification_rules' not in tables:
        op.create_table(
            'notification_rules',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('rule_type', sa.String(50), nullable=False),
            sa.Column('threshold', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('level', sa.String(20), nullable=False, server_default='WARNING'),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('company_id', 'rule_type', name='uq_notification_rules_company_type'),
            sa.CheckConstraint('threshold >= 0', name='ck_notification_rules_threshold_nonnegative'),
            sa.CheckConstraint(
                "rule_type IN ('STOCK_BELOW_MIN','RECEIVABLE_OVERDUE','PAYABLE_DUE')",
                name='ck_notification_rules_type',
            ),
            sa.CheckConstraint("level IN ('INFO','WARNING','DANGER')", name='ck_notification_rules_level'),
        )
        op.create_index('ix_notification_rules_company_id', 'notification_rules', ['company_id'])
        op.create_index('ix_notification_rules_rule_type', 'notification_rules', ['rule_type'])

    inspector = sa.inspect(bind)
    product_cols = _columns(inspector, 'products')
    if 'archived_at' not in product_cols:
        op.add_column('products', sa.Column('archived_at', sa.DateTime()))
        op.create_index('ix_products_archived_at', 'products', ['archived_at'])
    if 'sales_tax_id' not in product_cols:
        op.add_column('products', sa.Column('sales_tax_id', sa.Integer(), sa.ForeignKey('sales_taxes.id')))

    client_cols = _columns(sa.inspect(bind), 'clients')
    if 'archived_at' not in client_cols:
        op.add_column('clients', sa.Column('archived_at', sa.DateTime()))
        op.create_index('ix_clients_archived_at', 'clients', ['archived_at'])

    supplier_cols = _columns(sa.inspect(bind), 'suppliers')
    if 'archived_at' not in supplier_cols:
        op.add_column('suppliers', sa.Column('archived_at', sa.DateTime()))
        op.create_index('ix_suppliers_archived_at', 'suppliers', ['archived_at'])

    sale_cols = _columns(sa.inspect(bind), 'sales')
    if 'quote_valid_until' not in sale_cols:
        op.add_column('sales', sa.Column('quote_valid_until', sa.Date()))
    if 'quote_notes' not in sale_cols:
        op.add_column('sales', sa.Column('quote_notes', sa.String(500)))
    if 'promotion_id' not in sale_cols:
        op.add_column('sales', sa.Column('promotion_id', sa.Integer(), sa.ForeignKey('promotions.id')))
    if 'discount_amount' not in sale_cols:
        op.add_column('sales', sa.Column('discount_amount', sa.Numeric(10, 2), nullable=False, server_default='0'))
    sale_constraints = {constraint.get('name') for constraint in sa.inspect(bind).get_check_constraints('sales')}
    if 'ck_sales_discount_nonnegative' not in sale_constraints:
        op.create_check_constraint('ck_sales_discount_nonnegative', 'sales', 'discount_amount >= 0')

    item_cols = _columns(sa.inspect(bind), 'sale_items')
    if 'tax_name' not in item_cols:
        op.add_column('sale_items', sa.Column('tax_name', sa.String(80), nullable=False, server_default='ITBIS 18%'))
    if 'tax_rate' not in item_cols:
        op.add_column('sale_items', sa.Column('tax_rate', sa.Numeric(5, 2), nullable=False, server_default='18'))
    if 'tax_included' not in item_cols:
        op.add_column('sale_items', sa.Column('tax_included', sa.Boolean(), nullable=False, server_default=sa.true()))

    # Every existing company gets a sensible default tax without changing old sale totals.
    op.execute(sa.text("""
        INSERT INTO sales_taxes (company_id, name, rate, price_included, active, is_default, created_at)
        SELECT id, 'ITBIS 18%', 18, TRUE, TRUE, TRUE, NOW()
        FROM companies c
        WHERE NOT EXISTS (SELECT 1 FROM sales_taxes t WHERE t.company_id = c.id)
    """))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    sale_constraints = {constraint.get('name') for constraint in inspector.get_check_constraints('sales')}
    if 'ck_sales_discount_nonnegative' in sale_constraints:
        op.drop_constraint('ck_sales_discount_nonnegative', 'sales', type_='check')
    for table, columns in (
        ('sale_items', ('tax_included', 'tax_rate', 'tax_name')),
        ('sales', ('discount_amount', 'promotion_id', 'quote_notes', 'quote_valid_until')),
        ('suppliers', ('archived_at',)), ('clients', ('archived_at',)),
        ('products', ('sales_tax_id', 'archived_at')),
    ):
        existing = {c['name'] for c in sa.inspect(bind).get_columns(table)}
        for column in columns:
            if column in existing:
                op.drop_column(table, column)
    for table in ('notification_rules', 'company_documents', 'cash_sessions', 'promotions', 'sales_taxes'):
        if table in set(sa.inspect(bind).get_table_names()):
            op.drop_table(table)
