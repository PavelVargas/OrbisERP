from decimal import Decimal
from db import db

class PurchaseOrderItem(db.Model):
    __tablename__ = 'purchase_order_items'

    id = db.Column(db.Integer, primary_key=True)

    purchase_order_id = db.Column(
        db.Integer,
        db.ForeignKey('purchase_orders.id'),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey('products.id'),
        nullable=False
    )

    quantity = db.Column(db.Integer, nullable=False)

    quantity_received = db.Column(db.Integer, default=0)

    unit_cost = db.Column(db.Numeric(10, 2), nullable=False)
    tax_name = db.Column(db.String(80), nullable=False, default='Exento')
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    tax_included = db.Column(db.Boolean, nullable=False, default=False)

    purchase_order = db.relationship('PurchaseOrder', backref='items')
    product = db.relationship('Product', backref='purchase_items')

    # ✅ SUBTOTAL CALCULADO
    @property
    def subtotal(self):
        return Decimal(self.quantity) * Decimal(self.unit_cost)

    @property
    def tax_amount(self):
        base = self.subtotal
        rate = Decimal(self.tax_rate or 0)
        if rate <= 0:
            return Decimal('0.00')
        if self.tax_included:
            return (base - (base / (Decimal('1') + rate / Decimal('100')))).quantize(Decimal('0.01'))
        return (base * rate / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def net_subtotal(self):
        return self.subtotal - self.tax_amount if self.tax_included else self.subtotal

    @property
    def line_total(self):
        return self.subtotal if self.tax_included else self.subtotal + self.tax_amount
