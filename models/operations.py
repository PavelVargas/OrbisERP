from services.time_utils import utcnow
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
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


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
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class SecurityAttempt(db.Model):
    """Persistent authentication throttle shared by every web worker."""
    __tablename__ = 'security_attempts'
    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(80), nullable=False, index=True)
    subject_hash = db.Column(db.String(64), nullable=False, index=True)
    attempted_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


class RequestIdempotency(db.Model):
    """One-time mutation key shared by all workers and application instances."""
    __tablename__ = 'request_idempotency'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'user_id', 'request_key', name='uq_idempotency_tenant_user_key'),
    )
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    request_key = db.Column(db.String(100), nullable=False)
    endpoint = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


class UserSession(db.Model):
    """Server-side registry used to revoke individual signed-cookie sessions."""
    __tablename__ = 'user_sessions'
    id = db.Column(db.Integer, primary_key=True)
    session_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, nullable=True, index=True)
    revoke_reason = db.Column(db.String(120), nullable=True)

    user = db.relationship('User')

    @property
    def is_active(self):
        return self.revoked_at is None


class OperationJob(db.Model):
    """Observable record for imports, exports and other long-running work."""
    __tablename__ = 'operation_jobs'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    job_type = db.Column(db.String(50), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='PENDING', index=True)
    progress = db.Column(db.Integer, nullable=False, default=0)
    total_rows = db.Column(db.Integer, nullable=False, default=0)
    processed_rows = db.Column(db.Integer, nullable=False, default=0)
    error_count = db.Column(db.Integer, nullable=False, default=0)
    error_summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User')

    __table_args__ = (
        db.CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED')", name='ck_operation_jobs_status'),
        db.CheckConstraint('progress >= 0 AND progress <= 100', name='ck_operation_jobs_progress'),
        db.CheckConstraint('total_rows >= 0 AND processed_rows >= 0 AND error_count >= 0', name='ck_operation_jobs_counts'),
    )
