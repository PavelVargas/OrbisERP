from db import db
from datetime import datetime

class PurchaseReturn(db.Model):
    __tablename__ = 'purchase_returns'

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
