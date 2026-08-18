from datetime import datetime

from db import db


class PurchaseTax(db.Model):
    __tablename__ = 'purchase_taxes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    price_included = db.Column(db.Boolean, nullable=False, default=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('company_id', 'name', name='uq_purchase_tax_company_name'),
    )

