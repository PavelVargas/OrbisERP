"""Retail 2.0 domain models.

The module keeps the existing ERP core compatible while adding optional retail
capabilities (branches, terminals, variants, UOM, pricing, tracking, loyalty,
layaway, APIs and approval workflows). All tenant-owned records carry company_id.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import secrets

from db import db
from services.time_utils import utcnow


class CompanyRetailSettings(db.Model):
    __tablename__ = 'company_retail_settings'
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), primary_key=True)
    industry_profile = db.Column(db.String(30), nullable=False, default='GENERAL')
    enable_variants = db.Column(db.Boolean, nullable=False, default=True)
    enable_uom = db.Column(db.Boolean, nullable=False, default=True)
    enable_price_lists = db.Column(db.Boolean, nullable=False, default=True)
    enable_lots = db.Column(db.Boolean, nullable=False, default=False)
    enable_serials = db.Column(db.Boolean, nullable=False, default=False)
    enable_expirations = db.Column(db.Boolean, nullable=False, default=False)
    enable_warranties = db.Column(db.Boolean, nullable=False, default=True)
    enable_bundles = db.Column(db.Boolean, nullable=False, default=True)
    enable_credit = db.Column(db.Boolean, nullable=False, default=True)
    enable_loyalty = db.Column(db.Boolean, nullable=False, default=False)
    enable_gift_cards = db.Column(db.Boolean, nullable=False, default=False)
    enable_terminals = db.Column(db.Boolean, nullable=False, default=True)
    enable_layaway = db.Column(db.Boolean, nullable=False, default=False)
    enable_replenishment = db.Column(db.Boolean, nullable=False, default=True)
    costing_method = db.Column(db.String(20), nullable=False, default='AVERAGE')
    default_receipt_width = db.Column(db.Integer, nullable=False, default=80)
    receipt_printer_mode = db.Column(db.String(20), nullable=False, default='BROWSER')
    receipt_printer_name = db.Column(db.String(160), nullable=True)
    receipt_auto_print = db.Column(db.Boolean, nullable=False, default=False)
    loyalty_points_per_currency = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    loyalty_currency_per_point = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    company = db.relationship('Company', backref=db.backref('retail_settings', uselist=False, cascade='all, delete-orphan'))

    __table_args__ = (
        db.CheckConstraint("industry_profile IN ('GENERAL','FASHION','TECH','HARDWARE','GROCERY','DISTRIBUTION','COSMETICS','FURNITURE','OTHER')", name='ck_retail_profile'),
        db.CheckConstraint("costing_method IN ('AVERAGE','FIFO','LAST')", name='ck_retail_costing_method'),
        db.CheckConstraint('default_receipt_width BETWEEN 40 AND 112', name='ck_retail_receipt_width'),
        db.CheckConstraint("receipt_printer_mode IN ('BROWSER','WEBUSB','ELECTRON')", name='ck_retail_printer_mode'),
        db.CheckConstraint('loyalty_points_per_currency >= 0 AND loyalty_currency_per_point >= 0', name='ck_retail_loyalty_rates'),
    )


class Branch(db.Model):
    __tablename__ = 'branches'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'code', name='uq_branch_company_code'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    code = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    phone = db.Column(db.String(40))
    status = db.Column(db.Boolean, nullable=False, default=True)
    is_main = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    company = db.relationship('Company', backref=db.backref('branches', lazy=True))


class PosTerminal(db.Model):
    __tablename__ = 'pos_terminals'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'code', name='uq_terminal_company_code'),
        db.CheckConstraint('receipt_width BETWEEN 40 AND 112', name='ck_terminal_receipt_width'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    code = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    receipt_width = db.Column(db.Integer, nullable=False, default=80)
    status = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    branch = db.relationship('Branch', backref=db.backref('terminals', lazy=True))
    warehouse = db.relationship('Warehouse', backref=db.backref('terminals', lazy=True))


class UnitOfMeasure(db.Model):
    __tablename__ = 'units_of_measure'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'name', 'category', name='uq_uom_company_name_category'),
        db.CheckConstraint('factor_to_reference > 0', name='ck_uom_factor_positive'),
        db.CheckConstraint('rounding > 0', name='ck_uom_rounding_positive'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(40), nullable=False, default='UNIT')
    factor_to_reference = db.Column(db.Numeric(18, 6), nullable=False, default=1)
    rounding = db.Column(db.Numeric(12, 6), nullable=False, default=1)
    allow_fraction = db.Column(db.Boolean, nullable=False, default=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ProductUomConversion(db.Model):
    __tablename__ = 'product_uom_conversions'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'product_id', 'uom_id', name='uq_product_uom_conversion'),
        db.CheckConstraint('factor_to_base > 0', name='ck_product_uom_factor_positive'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    uom_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'), nullable=False, index=True)
    factor_to_base = db.Column(db.Numeric(18, 6), nullable=False, default=1)
    allow_sale = db.Column(db.Boolean, nullable=False, default=True)
    allow_purchase = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    product = db.relationship('Product', backref=db.backref('uom_conversions', lazy=True, cascade='all, delete-orphan'))
    uom = db.relationship('UnitOfMeasure')


class ProductAttribute(db.Model):
    __tablename__ = 'product_attributes'
    __table_args__ = (db.UniqueConstraint('company_id', 'name', name='uq_product_attribute_company_name'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    display_type = db.Column(db.String(20), nullable=False, default='SELECT')
    sequence = db.Column(db.Integer, nullable=False, default=10)
    active = db.Column(db.Boolean, nullable=False, default=True)

    values = db.relationship('ProductAttributeValue', back_populates='attribute', cascade='all, delete-orphan', order_by='ProductAttributeValue.sequence')


class ProductAttributeValue(db.Model):
    __tablename__ = 'product_attribute_values'
    __table_args__ = (db.UniqueConstraint('attribute_id', 'value', name='uq_product_attribute_value'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    attribute_id = db.Column(db.Integer, db.ForeignKey('product_attributes.id'), nullable=False, index=True)
    value = db.Column(db.String(80), nullable=False)
    color_hex = db.Column(db.String(7))
    sequence = db.Column(db.Integer, nullable=False, default=10)
    active = db.Column(db.Boolean, nullable=False, default=True)

    attribute = db.relationship('ProductAttribute', back_populates='values')


class ProductVariant(db.Model):
    __tablename__ = 'product_variants'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'sku', name='uq_product_variant_company_sku'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    sku = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    price_extra = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    cost_extra = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    image_path = db.Column(db.String(255))
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    product = db.relationship('Product', backref=db.backref('variants', lazy=True, cascade='all, delete-orphan'))
    values = db.relationship('ProductVariantValue', back_populates='variant', cascade='all, delete-orphan')

    @property
    def display_price(self):
        return Decimal(self.product.price or 0) + Decimal(self.price_extra or 0)

    @property
    def display_cost(self):
        return Decimal(self.product.cost or 0) + Decimal(self.cost_extra or 0)

    @property
    def attribute_summary(self):
        pairs = sorted((link.attribute_value.attribute.name, link.attribute_value.value) for link in self.values if link.attribute_value)
        return ' / '.join(value for _, value in pairs)


class ProductVariantValue(db.Model):
    __tablename__ = 'product_variant_values'
    __table_args__ = (db.UniqueConstraint('variant_id', 'attribute_value_id', name='uq_variant_attribute_value'),)
    id = db.Column(db.Integer, primary_key=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=False, index=True)
    attribute_value_id = db.Column(db.Integer, db.ForeignKey('product_attribute_values.id'), nullable=False, index=True)

    variant = db.relationship('ProductVariant', back_populates='values')
    attribute_value = db.relationship('ProductAttributeValue')


class ProductBarcode(db.Model):
    __tablename__ = 'product_barcodes'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'code', name='uq_product_barcode_company_code'),
        db.CheckConstraint("barcode_type IN ('EAN13','EAN8','UPC','CODE128','QR','INTERNAL','SUPPLIER')", name='ck_product_barcode_type'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    code = db.Column(db.String(120), nullable=False)
    barcode_type = db.Column(db.String(20), nullable=False, default='CODE128')
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    product = db.relationship('Product', backref=db.backref('barcodes', lazy=True, cascade='all, delete-orphan'))
    variant = db.relationship('ProductVariant', backref=db.backref('barcodes', lazy=True, cascade='all, delete-orphan'))


class WarehouseVariantStock(db.Model):
    __tablename__ = 'warehouse_variant_stock'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'warehouse_id', 'variant_id', name='uq_warehouse_variant_stock'),
        db.CheckConstraint('quantity >= 0', name='ck_warehouse_variant_stock_nonnegative'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=False, index=True)
    quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)

    warehouse = db.relationship('Warehouse')
    product = db.relationship('Product')
    variant = db.relationship('ProductVariant', backref=db.backref('warehouse_stocks', lazy=True, cascade='all, delete-orphan'))


class PriceList(db.Model):
    __tablename__ = 'price_lists'
    __table_args__ = (db.UniqueConstraint('company_id', 'code', name='uq_price_list_company_code'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    code = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    currency_code = db.Column(db.String(3), nullable=False, default='DOP')
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    rules = db.relationship('PriceListRule', back_populates='price_list', cascade='all, delete-orphan')


class PriceListRule(db.Model):
    __tablename__ = 'price_list_rules'
    __table_args__ = (
        db.CheckConstraint('min_quantity > 0', name='ck_price_rule_qty_positive'),
        db.CheckConstraint("rule_type IN ('FIXED','DISCOUNT','SURCHARGE')", name='ck_price_rule_type'),
        db.CheckConstraint(
            'percent IS NULL OR (percent >= 0 AND percent <= 100)',
            name='ck_price_rule_percent_range',
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    price_list_id = db.Column(db.Integer, db.ForeignKey('price_lists.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True, index=True)
    min_quantity = db.Column(db.Numeric(14, 3), nullable=False, default=1)
    rule_type = db.Column(db.String(20), nullable=False, default='FIXED')
    fixed_price = db.Column(db.Numeric(12, 2))
    percent = db.Column(db.Numeric(7, 3))
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)
    priority = db.Column(db.Integer, nullable=False, default=10)
    active = db.Column(db.Boolean, nullable=False, default=True)

    price_list = db.relationship('PriceList', back_populates='rules')
    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')
    category = db.relationship('Category')


class ProductSupplier(db.Model):
    __tablename__ = 'product_suppliers'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'product_id', 'variant_id', 'supplier_id', name='uq_product_supplier'),
        db.CheckConstraint('unit_cost >= 0 AND min_quantity > 0 AND lead_time_days >= 0', name='ck_product_supplier_values'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False, index=True)
    supplier_sku = db.Column(db.String(80))
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    min_quantity = db.Column(db.Numeric(14, 3), nullable=False, default=1)
    lead_time_days = db.Column(db.Integer, nullable=False, default=0)
    preferred = db.Column(db.Boolean, nullable=False, default=False)

    product = db.relationship('Product', backref=db.backref('supplier_links', lazy=True, cascade='all, delete-orphan'))
    variant = db.relationship('ProductVariant')
    supplier = db.relationship('Supplier', backref=db.backref('product_links', lazy=True, cascade='all, delete-orphan'))


class ProductBundleItem(db.Model):
    __tablename__ = 'product_bundle_items'
    __table_args__ = (
        db.UniqueConstraint('bundle_product_id', 'component_product_id', 'component_variant_id', name='uq_bundle_component'),
        db.CheckConstraint('quantity > 0', name='ck_bundle_item_qty_positive'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    bundle_product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    component_product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    component_variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)
    quantity = db.Column(db.Numeric(14, 3), nullable=False, default=1)

    bundle = db.relationship('Product', foreign_keys=[bundle_product_id], backref=db.backref('bundle_items', lazy=True, cascade='all, delete-orphan'))
    component = db.relationship('Product', foreign_keys=[component_product_id])
    component_variant = db.relationship('ProductVariant')


class InventoryLot(db.Model):
    __tablename__ = 'inventory_lots'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'product_id', 'variant_id', 'warehouse_id', 'lot_number', name='uq_inventory_lot'),
        db.CheckConstraint('quantity >= 0', name='ck_inventory_lot_qty_nonnegative'),
        db.CheckConstraint("status IN ('AVAILABLE','QUARANTINE','EXPIRED','DEPLETED')", name='ck_inventory_lot_status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    lot_number = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    manufactured_at = db.Column(db.Date)
    expires_at = db.Column(db.Date, index=True)
    received_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    status = db.Column(db.String(20), nullable=False, default='AVAILABLE')

    product = db.relationship('Product', backref=db.backref('lots', lazy=True))
    variant = db.relationship('ProductVariant')
    warehouse = db.relationship('Warehouse')


class InventorySerial(db.Model):
    __tablename__ = 'inventory_serials'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'serial_number', name='uq_inventory_serial_company_number'),
        db.CheckConstraint("status IN ('AVAILABLE','RESERVED','SOLD','WARRANTY','QUARANTINE','SCRAPPED')", name='ck_inventory_serial_status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True, index=True)
    serial_number = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='AVAILABLE')
    acquired_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    sold_at = db.Column(db.DateTime)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=True, index=True)
    warranty_until = db.Column(db.Date)
    notes = db.Column(db.String(255))

    product = db.relationship('Product', backref=db.backref('serials', lazy=True))
    variant = db.relationship('ProductVariant')
    warehouse = db.relationship('Warehouse')
    sale_item = db.relationship('SaleItem', backref=db.backref('serials', lazy=True))


class WarrantyClaim(db.Model):
    __tablename__ = 'warranty_claims'
    __table_args__ = (db.CheckConstraint("status IN ('OPEN','IN_REVIEW','APPROVED','REPLACED','REPAIRED','REJECTED','CLOSED')", name='ck_warranty_claim_status'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    serial_id = db.Column(db.Integer, db.ForeignKey('inventory_serials.id'), nullable=True, index=True)
    replacement_serial_id = db.Column(db.Integer, db.ForeignKey('inventory_serials.id'), nullable=True, index=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default='OPEN')
    reason = db.Column(db.String(255), nullable=False)
    resolution = db.Column(db.String(255))
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    opened_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    closed_at = db.Column(db.DateTime)

    serial = db.relationship('InventorySerial', foreign_keys=[serial_id])
    replacement_serial = db.relationship('InventorySerial', foreign_keys=[replacement_serial_id])
    sale_item = db.relationship('SaleItem')
    client = db.relationship('Client')
    resolver = db.relationship('User', foreign_keys=[resolved_by])


class SalePayment(db.Model):
    __tablename__ = 'sale_payments'
    __table_args__ = (
        db.CheckConstraint('amount > 0', name='ck_sale_payment_amount_positive'),
        db.CheckConstraint("method IN ('CASH','CARD','TRANSFER','CREDIT','GIFT_CARD','LOYALTY','OTHER')", name='ck_sale_payment_method'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    method = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reference = db.Column(db.String(120))
    gift_card_id = db.Column(db.Integer, db.ForeignKey('gift_cards.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    sale = db.relationship('Sale', backref=db.backref('payments', lazy=True, cascade='all, delete-orphan'))
    gift_card = db.relationship('GiftCard')


class GiftCard(db.Model):
    __tablename__ = 'gift_cards'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'code', name='uq_gift_card_company_code'),
        db.CheckConstraint('initial_balance >= 0 AND balance >= 0', name='ck_gift_card_balance'),
        db.CheckConstraint("status IN ('ACTIVE','BLOCKED','EXPIRED','DEPLETED')", name='ck_gift_card_status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True, index=True)
    code = db.Column(db.String(80), nullable=False)
    initial_balance = db.Column(db.Numeric(12, 2), nullable=False)
    balance = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='ACTIVE')
    expires_at = db.Column(db.Date)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    client = db.relationship('Client', backref=db.backref('gift_cards', lazy=True))


class LoyaltyTransaction(db.Model):
    __tablename__ = 'loyalty_transactions'
    __table_args__ = (
        db.CheckConstraint("event_type IN ('EARN','REDEEM','ADJUST','EXPIRE')", name='ck_loyalty_event_type'),
        db.CheckConstraint(
            'points >= -9999999999.9999 AND points <= 9999999999.9999 '
            'AND balance_after >= 0 AND balance_after <= 9999999999.9999',
            name='ck_loyalty_transaction_points_range',
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True, index=True)
    event_type = db.Column(db.String(20), nullable=False)
    points = db.Column(db.Numeric(14, 4), nullable=False)
    balance_after = db.Column(db.Numeric(14, 4), nullable=False)
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    client = db.relationship('Client', backref=db.backref('loyalty_transactions', lazy=True))
    sale = db.relationship('Sale')


class Layaway(db.Model):
    __tablename__ = 'layaways'
    __table_args__ = (
        db.UniqueConstraint('sale_id', name='uq_layaway_sale'),
        db.CheckConstraint("status IN ('OPEN','COMPLETED','CANCELLED','EXPIRED')", name='ck_layaway_status'),
        db.CheckConstraint('deposit_amount >= 0 AND balance >= 0', name='ck_layaway_amounts'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False, index=True)
    deposit_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default='OPEN')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime)

    sale = db.relationship('Sale', backref=db.backref('layaway', uselist=False))
    client = db.relationship('Client', backref=db.backref('layaways', lazy=True))


class StockReservation(db.Model):
    __tablename__ = 'stock_reservations'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'sale_item_id', name='uq_stock_reservation_sale_item'),
        db.CheckConstraint('quantity > 0', name='ck_stock_reservation_qty_positive'),
        db.CheckConstraint("status IN ('ACTIVE','RELEASED','CONSUMED')", name='ck_stock_reservation_status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='ACTIVE')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    sale_item = db.relationship('SaleItem')
    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')
    warehouse = db.relationship('Warehouse')


class ApprovalRule(db.Model):
    __tablename__ = 'approval_rules'
    __table_args__ = (
        db.CheckConstraint("operation_type IN ('DISCOUNT','PURCHASE','STOCK_ADJUST','RETURN','EXPENSE')", name='ck_approval_rule_operation'),
        db.CheckConstraint('threshold_amount >= 0', name='ck_approval_rule_threshold'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    operation_type = db.Column(db.String(30), nullable=False)
    threshold_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    required_role = db.Column(db.String(40), nullable=False, default='admin')
    active = db.Column(db.Boolean, nullable=False, default=True)


class ApprovalRequest(db.Model):
    __tablename__ = 'approval_requests'
    __table_args__ = (db.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','CANCELLED')", name='ck_approval_request_status'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('approval_rules.id'), nullable=False)
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='PENDING')
    reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    resolved_at = db.Column(db.DateTime)

    rule = db.relationship('ApprovalRule')
    requester = db.relationship('User', foreign_keys=[requested_by])
    approver = db.relationship('User', foreign_keys=[approved_by])


class InventoryCostLayer(db.Model):
    __tablename__ = 'inventory_cost_layers'
    __table_args__ = (
        db.CheckConstraint('quantity_remaining >= 0 AND unit_cost >= 0', name='ck_inventory_cost_layer_values'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    purchase_item_id = db.Column(db.Integer, db.ForeignKey('purchase_order_items.id'), nullable=True, index=True)
    quantity_remaining = db.Column(db.Numeric(14, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(12, 4), nullable=False)
    received_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')
    warehouse = db.relationship('Warehouse')
    purchase_item = db.relationship('PurchaseOrderItem')


class ApiKey(db.Model):
    __tablename__ = 'api_keys'
    __table_args__ = (db.UniqueConstraint('key_hash', name='uq_api_key_hash'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    key_prefix = db.Column(db.String(16), nullable=False, index=True)
    key_hash = db.Column(db.String(64), nullable=False)
    scopes = db.Column(db.String(500), nullable=False, default='products:read,inventory:read')
    active = db.Column(db.Boolean, nullable=False, default=True)
    last_used_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @staticmethod
    def generate_secret():
        raw = 'orb_' + secrets.token_urlsafe(32)
        return raw, raw[:12], hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def allows(self, scope):
        values = {item.strip() for item in (self.scopes or '').split(',') if item.strip()}
        return '*' in values or scope in values


class OutboundWebhook(db.Model):
    __tablename__ = 'outbound_webhooks'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    target_url = db.Column(db.String(500), nullable=False)
    secret = db.Column(db.String(120), nullable=False)
    event_types = db.Column(db.String(500), nullable=False, default='sale.completed')
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

class SaleItemLotAllocation(db.Model):
    __tablename__ = 'sale_item_lot_allocations'
    __table_args__ = (
        db.UniqueConstraint('sale_item_id', 'lot_id', name='uq_sale_item_lot'),
        db.CheckConstraint('quantity > 0', name='ck_sale_item_lot_qty_positive'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=False, index=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('inventory_lots.id'), nullable=False, index=True)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    sale_item = db.relationship('SaleItem', backref=db.backref('lot_allocations', lazy=True, cascade='all, delete-orphan'))
    lot = db.relationship('InventoryLot')

class LayawayPayment(db.Model):
    __tablename__ = 'layaway_payments'
    __table_args__ = (db.CheckConstraint('amount > 0', name='ck_layaway_payment_amount_positive'),)
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    layaway_id = db.Column(db.Integer, db.ForeignKey('layaways.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(20), nullable=False, default='CASH')
    reference = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    layaway = db.relationship('Layaway', backref=db.backref('payments', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User')


class InventoryConditionStock(db.Model):
    """Physical stock that is intentionally excluded from sellable availability.

    Used for damaged/quarantine returns and manual quality holds.  Keeping these
    quantities outside ``warehouse_stock`` prevents POS availability from
    accidentally selling merchandise that is physically present but not usable.
    """
    __tablename__ = 'inventory_condition_stock'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'warehouse_id', 'product_id', 'variant_id', 'condition', name='uq_inventory_condition_stock'),
        db.CheckConstraint('quantity >= 0', name='ck_inventory_condition_stock_nonnegative'),
        db.CheckConstraint("condition IN ('QUARANTINE','DAMAGED')", name='ck_inventory_condition_stock_condition'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    condition = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    warehouse = db.relationship('Warehouse')
    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')


class SaleReturnItemLotAllocation(db.Model):
    """Exact lot quantities returned from a sale line."""
    __tablename__ = 'sale_return_item_lot_allocations'
    __table_args__ = (
        db.UniqueConstraint('return_item_id', 'lot_id', name='uq_return_item_lot'),
        db.CheckConstraint('quantity > 0', name='ck_return_item_lot_qty_positive'),
        db.CheckConstraint("disposition IN ('AVAILABLE','QUARANTINE','DAMAGED','NONE')", name='ck_return_item_lot_disposition'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    return_item_id = db.Column(db.Integer, db.ForeignKey('sale_return_items.id'), nullable=False, index=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=False, index=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('inventory_lots.id'), nullable=False, index=True)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    disposition = db.Column(db.String(20), nullable=False, default='AVAILABLE')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    return_item = db.relationship('SaleReturnItem', backref=db.backref('lot_returns', lazy=True, cascade='all, delete-orphan'))
    sale_item = db.relationship('SaleItem')
    lot = db.relationship('InventoryLot')


class SaleReturnItemSerial(db.Model):
    """Serial/IMEI units selected in a return."""
    __tablename__ = 'sale_return_item_serials'
    __table_args__ = (
        db.UniqueConstraint('return_item_id', 'serial_id', name='uq_return_item_serial'),
        db.CheckConstraint("disposition IN ('AVAILABLE','QUARANTINE','DAMAGED','NONE')", name='ck_return_item_serial_disposition'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    return_item_id = db.Column(db.Integer, db.ForeignKey('sale_return_items.id'), nullable=False, index=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=False, index=True)
    serial_id = db.Column(db.Integer, db.ForeignKey('inventory_serials.id'), nullable=False, index=True)
    disposition = db.Column(db.String(20), nullable=False, default='AVAILABLE')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    return_item = db.relationship('SaleReturnItem', backref=db.backref('serial_returns', lazy=True, cascade='all, delete-orphan'))
    sale_item = db.relationship('SaleItem')
    serial = db.relationship('InventorySerial')


class InventorySerialEvent(db.Model):
    """Append-only lifecycle history for a serial/IMEI."""
    __tablename__ = 'inventory_serial_events'
    __table_args__ = (
        db.CheckConstraint("event_type IN ('RECEIVED','RESERVED','SOLD','RETURNED','WARRANTY_OPEN','WARRANTY_UPDATE','ADJUSTED')", name='ck_inventory_serial_event_type'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    serial_id = db.Column(db.Integer, db.ForeignKey('inventory_serials.id'), nullable=False, index=True)
    event_type = db.Column(db.String(30), nullable=False)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=True, index=True)
    return_item_id = db.Column(db.Integer, db.ForeignKey('sale_return_items.id'), nullable=True, index=True)
    warranty_claim_id = db.Column(db.Integer, db.ForeignKey('warranty_claims.id'), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True, index=True)
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    serial = db.relationship('InventorySerial', backref=db.backref('events', lazy=True, order_by='InventorySerialEvent.created_at'))
    sale_item = db.relationship('SaleItem')
    return_item = db.relationship('SaleReturnItem')
    warranty_claim = db.relationship('WarrantyClaim')
    warehouse = db.relationship('Warehouse')
