"""backoffice operations suite

Revision ID: c8f2a91d640e
Revises: b7e4a0d32591
"""
from alembic import op
import sqlalchemy as sa


revision = 'c8f2a91d640e'
down_revision = 'b7e4a0d32591'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    company_columns = {c['name'] for c in inspector.get_columns('companies')}
    if 'fiscal_mode' not in company_columns:
        op.add_column('companies', sa.Column('fiscal_mode', sa.String(20), nullable=False, server_default='disabled'))
    if 'fiscal_disclaimer' not in company_columns:
        op.add_column('companies', sa.Column('fiscal_disclaimer', sa.String(180), nullable=False, server_default='DOCUMENTO NO FISCAL'))
    user_columns = {c['name'] for c in inspector.get_columns('users')}
    if 'totp_secret' not in user_columns:
        op.add_column('users', sa.Column('totp_secret', sa.String(64), nullable=True))
    if 'two_factor_enabled' not in user_columns:
        op.add_column('users', sa.Column('two_factor_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    product_columns = {c['name'] for c in inspector.get_columns('products')}
    if 'min_stock' not in product_columns:
        op.add_column('products', sa.Column('min_stock', sa.Integer(), nullable=False, server_default='5'))
    if 'max_stock' not in product_columns:
        op.add_column('products', sa.Column('max_stock', sa.Integer(), nullable=True))

    tables = set(inspector.get_table_names())
    if 'audit_logs' not in tables:
        op.create_table('audit_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id')),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
            sa.Column('action', sa.String(255)), sa.Column('description', sa.Text()),
            sa.Column('created_at', sa.DateTime()), sa.Column('ip_address', sa.String(50)),
        )
    if 'global_announcements' not in tables:
        op.create_table('global_announcements',
            sa.Column('id', sa.Integer(), primary_key=True), sa.Column('message', sa.String(500), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
            sa.Column('type', sa.String(20), server_default='info'), sa.Column('created_at', sa.DateTime()),
        )
    if 'superadmin_logs' not in tables:
        op.create_table('superadmin_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('admin_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id')),
            sa.Column('action', sa.String(255), nullable=False), sa.Column('description', sa.Text()),
            sa.Column('ip_address', sa.String(50)), sa.Column('created_at', sa.DateTime()),
        )
    if 'sale_returns' not in tables:
        op.create_table('sale_returns',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('reason', sa.String(255), nullable=False),
            sa.Column('refund_method', sa.String(30), nullable=False, server_default='ORIGINAL'),
            sa.Column('total_refund', sa.Numeric(12, 2), nullable=False, server_default='0'),
            sa.Column('restocked', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('status', sa.String(20), nullable=False, server_default='COMPLETED'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_sale_returns_company_id', 'sale_returns', ['company_id'])
        op.create_index('ix_sale_returns_sale_id', 'sale_returns', ['sale_id'])
    if 'sale_return_items' not in tables:
        op.create_table('sale_return_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('return_id', sa.Integer(), sa.ForeignKey('sale_returns.id'), nullable=False),
            sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=True),
            sa.Column('quantity', sa.Integer(), nullable=False),
            sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        )
        op.create_index('ix_sale_return_items_return_id', 'sale_return_items', ['return_id'])
    if 'customer_payments' not in tables:
        op.create_table('customer_payments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=True),
            sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('method', sa.String(30), nullable=False),
            sa.Column('reference', sa.String(100)), sa.Column('notes', sa.String(255)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_customer_payments_company_id', 'customer_payments', ['company_id'])
        op.create_index('ix_customer_payments_sale_id', 'customer_payments', ['sale_id'])
    if 'supplier_bills' not in tables:
        op.create_table('supplier_bills',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=False),
            sa.Column('purchase_order_id', sa.Integer(), sa.ForeignKey('purchase_orders.id')),
            sa.Column('document_number', sa.String(80), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('paid_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
            sa.Column('due_date', sa.Date()), sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
            sa.Column('notes', sa.String(255)), sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('company_id', 'document_number', name='uq_supplier_bill_company_document'),
        )
        op.create_index('ix_supplier_bills_company_id', 'supplier_bills', ['company_id'])
        op.create_index('ix_supplier_bills_supplier_id', 'supplier_bills', ['supplier_id'])
    if 'supplier_payments' not in tables:
        op.create_table('supplier_payments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('bill_id', sa.Integer(), sa.ForeignKey('supplier_bills.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('method', sa.String(30), nullable=False), sa.Column('reference', sa.String(100)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_supplier_payments_company_id', 'supplier_payments', ['company_id'])
        op.create_index('ix_supplier_payments_bill_id', 'supplier_payments', ['bill_id'])
    if 'expenses' not in tables:
        op.create_table('expenses',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id')),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('category', sa.String(80), nullable=False), sa.Column('description', sa.String(255), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False), sa.Column('payment_method', sa.String(30), nullable=False),
            sa.Column('reference', sa.String(100)), sa.Column('expense_date', sa.Date(), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='POSTED'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_expenses_company_id', 'expenses', ['company_id'])
    if 'inventory_counts' not in tables:
        op.create_table('inventory_counts',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('warehouse_id', sa.Integer(), sa.ForeignKey('warehouses.id'), nullable=False),
            sa.Column('location_id', sa.Integer(), sa.ForeignKey('warehouse_locations.id')),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id')),
            sa.Column('status', sa.String(20), nullable=False, server_default='DRAFT'),
            sa.Column('notes', sa.String(255)), sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('approved_at', sa.DateTime()),
        )
        op.create_index('ix_inventory_counts_company_id', 'inventory_counts', ['company_id'])
    if 'inventory_count_items' not in tables:
        op.create_table('inventory_count_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('count_id', sa.Integer(), sa.ForeignKey('inventory_counts.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('expected_quantity', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('counted_quantity', sa.Integer()),
            sa.UniqueConstraint('count_id', 'product_id', name='uq_inventory_count_product'),
        )
        op.create_index('ix_inventory_count_items_count_id', 'inventory_count_items', ['count_id'])
    if 'app_notifications' not in tables:
        op.create_table('app_notifications',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
            sa.Column('level', sa.String(20), nullable=False, server_default='INFO'),
            sa.Column('title', sa.String(120), nullable=False), sa.Column('message', sa.String(255), nullable=False),
            sa.Column('link', sa.String(255)), sa.Column('dedupe_key', sa.String(150)),
            sa.Column('read_at', sa.DateTime()), sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('company_id', 'dedupe_key', name='uq_notification_company_key'),
        )
        op.create_index('ix_app_notifications_company_id', 'app_notifications', ['company_id'])
        op.create_index('ix_app_notifications_user_id', 'app_notifications', ['user_id'])


def downgrade():
    for table in ('app_notifications', 'inventory_count_items', 'inventory_counts', 'expenses',
                  'supplier_payments', 'supplier_bills', 'customer_payments', 'sale_return_items', 'sale_returns'):
        if table in set(sa.inspect(op.get_bind()).get_table_names()):
            op.drop_table(table)
    for table, columns in (('products', ('max_stock', 'min_stock')), ('users', ('two_factor_enabled', 'totp_secret')),
                           ('companies', ('fiscal_disclaimer', 'fiscal_mode'))):
        existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
        for column in columns:
            if column in existing:
                op.drop_column(table, column)
