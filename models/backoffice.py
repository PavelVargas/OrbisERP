from services.time_utils import utcnow
from datetime import datetime
from decimal import Decimal

from db import db


class SaleReturn(db.Model):
    __tablename__ = 'sale_returns'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    refund_method = db.Column(db.String(30), nullable=False, default='ORIGINAL')
    total_refund = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    restocked = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(20), nullable=False, default='COMPLETED')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    sale = db.relationship('Sale')
    user = db.relationship('User')
    items = db.relationship('SaleReturnItem', back_populates='sale_return', cascade='all, delete-orphan')


class SaleReturnItem(db.Model):
    __tablename__ = 'sale_return_items'
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='ck_sale_return_items_quantity_positive'),
        db.CheckConstraint('unit_price >= 0', name='ck_sale_return_items_price_nonnegative'),
        db.CheckConstraint("disposition IN ('AVAILABLE','QUARANTINE','DAMAGED','NONE')", name='ck_sale_return_item_disposition'),
    )
    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey('sale_returns.id'), nullable=False, index=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    uom_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'), nullable=True)
    uom_factor = db.Column(db.Numeric(18, 6), nullable=False, default=1)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    disposition = db.Column(db.String(20), nullable=False, default='AVAILABLE')

    sale_return = db.relationship('SaleReturn', back_populates='items')
    sale_item = db.relationship('SaleItem')
    product = db.relationship('Product')
    warehouse = db.relationship('Warehouse')
    variant = db.relationship('ProductVariant')
    uom = db.relationship('UnitOfMeasure')

    @property
    def line_total(self):
        return Decimal(self.quantity or 0) * Decimal(self.unit_price or 0)


class CustomerPayment(db.Model):
    __tablename__ = 'customer_payments'
    __table_args__ = (db.CheckConstraint('amount > 0', name='ck_customer_payments_amount_positive'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(30), nullable=False)
    reference = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    client = db.relationship('Client')
    sale = db.relationship('Sale')
    user = db.relationship('User')


class SupplierBill(db.Model):
    __tablename__ = 'supplier_bills'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'document_number', name='uq_supplier_bill_company_document'),
        db.CheckConstraint('amount > 0', name='ck_supplier_bills_amount_positive'),
        db.CheckConstraint('paid_amount >= 0 AND paid_amount <= amount', name='ck_supplier_bills_paid_range'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False, index=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=True)
    document_number = db.Column(db.String(80), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    paid_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='PENDING')
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    supplier = db.relationship('Supplier')
    purchase_order = db.relationship('PurchaseOrder')
    payments = db.relationship('SupplierPayment', back_populates='bill', cascade='all, delete-orphan')

    @property
    def balance(self):
        return max(Decimal(self.amount or 0) - Decimal(self.paid_amount or 0), Decimal('0'))


class SupplierPayment(db.Model):
    __tablename__ = 'supplier_payments'
    __table_args__ = (db.CheckConstraint('amount > 0', name='ck_supplier_payments_amount_positive'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('supplier_bills.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(30), nullable=False)
    reference = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    bill = db.relationship('SupplierBill', back_populates='payments')
    user = db.relationship('User')


class Expense(db.Model):
    __tablename__ = 'expenses'
    __table_args__ = (db.CheckConstraint('amount > 0', name='ck_expenses_amount_positive'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False)
    reference = db.Column(db.String(100), nullable=True)
    expense_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='POSTED')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    supplier = db.relationship('Supplier')
    user = db.relationship('User')
    branch = db.relationship('Branch')


class InventoryCount(db.Model):
    __tablename__ = 'inventory_counts'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('warehouse_locations.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='DRAFT')
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)

    warehouse = db.relationship('Warehouse')
    location = db.relationship('WarehouseLocation')
    creator = db.relationship('User', foreign_keys=[created_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    items = db.relationship('InventoryCountItem', back_populates='inventory_count', cascade='all, delete-orphan')


class InventoryCountItem(db.Model):
    __tablename__ = 'inventory_count_items'
    __table_args__ = (
        db.UniqueConstraint('count_id', 'product_id', name='uq_inventory_count_product'),
        db.CheckConstraint('expected_quantity >= 0', name='ck_inventory_count_expected_nonnegative'),
        db.CheckConstraint('counted_quantity IS NULL OR counted_quantity >= 0', name='ck_inventory_count_counted_nonnegative'),
    )
    id = db.Column(db.Integer, primary_key=True)
    count_id = db.Column(db.Integer, db.ForeignKey('inventory_counts.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    expected_quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    counted_quantity = db.Column(db.Numeric(14, 3), nullable=True)

    inventory_count = db.relationship('InventoryCount', back_populates='items')
    product = db.relationship('Product')

    @property
    def difference(self):
        if self.counted_quantity is None:
            return None
        return self.counted_quantity - self.expected_quantity


class AppNotification(db.Model):
    __tablename__ = 'app_notifications'
    __table_args__ = (db.UniqueConstraint('company_id', 'dedupe_key', name='uq_notification_company_key'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    level = db.Column(db.String(20), nullable=False, default='INFO')
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    dedupe_key = db.Column(db.String(150), nullable=True)
    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship('User')
