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

    purchase_order = db.relationship('PurchaseOrder', backref='items')
    product = db.relationship('Product', backref='purchase_items')

    # ✅ SUBTOTAL CALCULADO
    @property
    def subtotal(self):
        return Decimal(self.quantity) * self.unit_cost