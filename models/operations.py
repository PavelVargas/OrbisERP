from datetime import datetime

from db import db


class BillingInvoice(db.Model):
    __tablename__ = 'billing_invoices'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    external_id = db.Column(db.String(120), nullable=False, unique=True)
    provider = db.Column(db.String(40), nullable=False, default='manual')
    status = db.Column(db.String(30), nullable=False, default='PENDING')
    plan_name = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default='DOP')
    period_start = db.Column(db.DateTime)
    period_end = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class SubscriptionEvent(db.Model):
    __tablename__ = 'subscription_events'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(150), nullable=False, unique=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), index=True)
    provider = db.Column(db.String(40), nullable=False, default='generic')
    event_type = db.Column(db.String(80), nullable=False)
    payload_hash = db.Column(db.String(64), nullable=False)
    processed = db.Column(db.Boolean, nullable=False, default=False)
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

