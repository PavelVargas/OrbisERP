from datetime import datetime
from db import db

class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'

    id = db.Column(db.Integer, primary_key=True)

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey('suppliers.id'),
        nullable=False
    )

    supplier_name = db.Column(db.String(150), nullable=False)

    status = db.Column(db.String(20), default='PENDING')
    total_items = db.Column(db.Integer, default=0)
    total_cost = db.Column(db.Numeric(12, 2), default=0)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    supplier = db.relationship('Supplier', backref='purchase_orders')

    def __repr__(self):
        return f'<PurchaseOrder #{self.id}>'
