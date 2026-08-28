"""integrity and session hardening

Revision ID: 2a6e8c4b1d70
Revises: 1f9c3a7e5b20
"""
from alembic import op
import sqlalchemy as sa


revision = '2a6e8c4b1d70'
down_revision = '1f9c3a7e5b20'
branch_labels = None
depends_on = None


def _constraint_names(inspector, table):
    return {
        item.get('name')
        for item in inspector.get_check_constraints(table)
        if item.get('name')
    }


def _add_check_not_valid(table, name, expression):
    """Protect every new write while allowing legacy data to be reviewed safely."""
    inspector = sa.inspect(op.get_bind())
    if name not in _constraint_names(inspector, table):
        op.execute(sa.text(
            f'ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID'
        ))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column['name'] for column in inspector.get_columns('users')}
    if 'is_active' not in user_columns:
        op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    if 'session_version' not in user_columns:
        op.add_column('users', sa.Column('session_version', sa.Integer(), nullable=False, server_default='1'))

    tables = set(inspector.get_table_names())
    if 'request_idempotency' not in tables:
        op.create_table(
            'request_idempotency',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('request_key', sa.String(100), nullable=False),
            sa.Column('endpoint', sa.String(150), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('company_id', 'user_id', 'request_key', name='uq_idempotency_tenant_user_key'),
        )
        op.create_index('ix_request_idempotency_company_id', 'request_idempotency', ['company_id'])
        op.create_index('ix_request_idempotency_user_id', 'request_idempotency', ['user_id'])
        op.create_index('ix_request_idempotency_created_at', 'request_idempotency', ['created_at'])
        tables.add('request_idempotency')

    checks = {
        'sales': {
            'ck_sales_subtotal_nonnegative': 'subtotal >= 0',
            'ck_sales_itbis_nonnegative': 'itbis >= 0',
            'ck_sales_total_nonnegative': 'total >= 0',
            'ck_sales_paid_nonnegative': 'amount_paid >= 0',
            'ck_sales_balance_nonnegative': 'balance >= 0',
            'ck_sales_status': "status IN ('DRAFT','PENDING','QUOTATION','COMPLETED','CANCELLED')",
            'ck_sales_company_required': 'company_id IS NOT NULL',
        },
        'sale_items': {
            'ck_sale_items_quantity_positive': 'quantity > 0',
            'ck_sale_items_price_nonnegative': 'price >= 0',
        },
        'warehouse_stock': {
            'ck_warehouse_stock_quantity_nonnegative': 'quantity >= 0',
        },
        'stock_transfers': {
            'ck_stock_transfers_quantity_positive': 'quantity > 0',
            'ck_stock_transfers_status': "status IN ('PENDING','RECEIVED','CANCELLED')",
        },
        'sale_return_items': {
            'ck_sale_return_items_quantity_positive': 'quantity > 0',
            'ck_sale_return_items_price_nonnegative': 'unit_price >= 0',
        },
        'customer_payments': {'ck_customer_payments_amount_positive': 'amount > 0'},
        'supplier_bills': {
            'ck_supplier_bills_amount_positive': 'amount > 0',
            'ck_supplier_bills_paid_range': 'paid_amount >= 0 AND paid_amount <= amount',
        },
        'supplier_payments': {'ck_supplier_payments_amount_positive': 'amount > 0'},
        'expenses': {'ck_expenses_amount_positive': 'amount > 0'},
        'inventory_count_items': {
            'ck_inventory_count_expected_nonnegative': 'expected_quantity >= 0',
            'ck_inventory_count_counted_nonnegative': 'counted_quantity IS NULL OR counted_quantity >= 0',
        },
    }
    for table, constraints in checks.items():
        if table in tables:
            for name, expression in constraints.items():
                _add_check_not_valid(table, name, expression)

    if 'warehouse_stock' in tables:
        uniques = {item.get('name') for item in inspector.get_unique_constraints('warehouse_stock')}
        if 'uq_warehouse_stock_tenant_product' not in uniques:
            # WarehouseStock ids have no business references; consolidate legacy
            # duplicates before making the invariant permanent.
            op.execute(sa.text('''
                UPDATE warehouse_stock target
                SET quantity = grouped.total_quantity
                FROM (
                    SELECT MIN(id) AS keep_id, company_id, warehouse_id, product_id,
                           SUM(quantity) AS total_quantity
                    FROM warehouse_stock
                    GROUP BY company_id, warehouse_id, product_id
                    HAVING COUNT(*) > 1
                ) grouped
                WHERE target.id = grouped.keep_id
            '''))
            op.execute(sa.text('''
                DELETE FROM warehouse_stock duplicate
                USING warehouse_stock keeper
                WHERE duplicate.id > keeper.id
                  AND duplicate.company_id = keeper.company_id
                  AND duplicate.warehouse_id = keeper.warehouse_id
                  AND duplicate.product_id = keeper.product_id
            '''))
            op.create_unique_constraint(
                'uq_warehouse_stock_tenant_product',
                'warehouse_stock',
                ['company_id', 'warehouse_id', 'product_id'],
            )

    if 'audit_logs' in tables:
        op.execute(sa.text('''
            CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_logs is append-only';
            END;
            $$ LANGUAGE plpgsql
        '''))
        op.execute(sa.text('DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs'))
        op.execute(sa.text('''
            CREATE TRIGGER trg_audit_logs_append_only
            BEFORE UPDATE OR DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation()
        '''))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if 'audit_logs' in tables:
        op.execute(sa.text('DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs'))
        op.execute(sa.text('DROP FUNCTION IF EXISTS prevent_audit_log_mutation()'))
    if 'request_idempotency' in tables:
        op.drop_table('request_idempotency')
    if 'warehouse_stock' in tables:
        uniques = {item.get('name') for item in inspector.get_unique_constraints('warehouse_stock')}
        if 'uq_warehouse_stock_tenant_product' in uniques:
            op.drop_constraint('uq_warehouse_stock_tenant_product', 'warehouse_stock', type_='unique')
    for table in (
        'inventory_count_items', 'expenses', 'supplier_payments', 'supplier_bills',
        'customer_payments', 'sale_return_items', 'stock_transfers', 'warehouse_stock',
        'sale_items', 'sales',
    ):
        if table not in tables:
            continue
        for constraint in list(_constraint_names(sa.inspect(bind), table)):
            if constraint.startswith('ck_'):
                op.drop_constraint(constraint, table, type_='check')
    user_columns = {column['name'] for column in sa.inspect(bind).get_columns('users')}
    if 'session_version' in user_columns:
        op.drop_column('users', 'session_version')
    if 'is_active' in user_columns:
        op.drop_column('users', 'is_active')
