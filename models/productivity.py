from services.time_utils import utcnow
from datetime import datetime

from sqlalchemy import text

from db import db


class CashSession(db.Model):
    __tablename__ = 'cash_sessions'
    __table_args__ = (
        db.CheckConstraint("status IN ('OPEN','CLOSED')", name='ck_cash_sessions_status'),
        db.CheckConstraint('opening_amount >= 0', name='ck_cash_sessions_opening_nonnegative'),
        db.CheckConstraint('counted_amount IS NULL OR counted_amount >= 0', name='ck_cash_sessions_counted_nonnegative'),
        db.Index(
            'uq_cash_sessions_open_user_branch', 'company_id', 'user_id', 'branch_id', unique=True,
            postgresql_where=text("status = 'OPEN'"),
            sqlite_where=text("status = 'OPEN'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    terminal_id = db.Column(db.Integer, db.ForeignKey('pos_terminals.id'), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default='OPEN', index=True)
    opening_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expected_amount = db.Column(db.Numeric(12, 2), nullable=True)
    counted_amount = db.Column(db.Numeric(12, 2), nullable=True)
    difference = db.Column(db.Numeric(12, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    opened_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    closed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User')
    branch = db.relationship('Branch')
    terminal = db.relationship('PosTerminal')


class DocumentFolder(db.Model):
    __tablename__ = 'document_folders'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('document_folders.id'), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    parent = db.relationship('DocumentFolder', remote_side=[id], backref=db.backref('children', lazy=True))
    user = db.relationship('User')


class CompanyDocument(db.Model):
    __tablename__ = 'company_documents'
    __table_args__ = (
        db.CheckConstraint(
            "entity_type IN ('COMPANY','PRODUCT','CLIENT','SUPPLIER','SALE','PURCHASE','EXPENSE')",
            name='ck_company_documents_entity_type',
        ),
        db.CheckConstraint('size_bytes >= 0', name='ck_company_documents_size_nonnegative'),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    entity_type = db.Column(db.String(40), nullable=False, default='COMPANY', index=True)
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    display_name = db.Column(db.String(180), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    mime_type = db.Column(db.String(100), nullable=True)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('document_folders.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship('User')
    folder = db.relationship('DocumentFolder', backref=db.backref('documents', lazy=True))


class NotificationRule(db.Model):
    __tablename__ = 'notification_rules'
    __table_args__ = (
        db.CheckConstraint('threshold >= 0', name='ck_notification_rules_threshold_nonnegative'),
        db.CheckConstraint("level IN ('INFO','WARNING','DANGER')", name='ck_notification_rules_level'),
        db.CheckConstraint("operator IS NULL OR operator IN ('LT','LTE','EQ','GTE','GT')", name='ck_notification_rules_operator'),
        db.CheckConstraint('lookback_days >= 0', name='ck_notification_rules_lookback_nonnegative'),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    rule_type = db.Column(db.String(50), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=True)
    threshold = db.Column(db.Integer, nullable=False, default=0)
    level = db.Column(db.String(20), nullable=False, default='WARNING')
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    custom_source = db.Column(db.String(30), nullable=True)
    operator = db.Column(db.String(8), nullable=True)
    lookback_days = db.Column(db.Integer, nullable=False, default=30)
    message = db.Column(db.String(255), nullable=True)
    link = db.Column(db.String(255), nullable=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    target_user = db.relationship('User', foreign_keys=[target_user_id])


class SalesTax(db.Model):
    __tablename__ = 'sales_taxes'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'name', name='uq_sales_taxes_company_name'),
        db.CheckConstraint('rate >= 0 AND rate <= 100', name='ck_sales_taxes_rate_range'),
        db.Index(
            'uq_sales_taxes_default_company', 'company_id', unique=True,
            postgresql_where=text('is_default = TRUE'),
            sqlite_where=text('is_default = TRUE'),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    price_included = db.Column(db.Boolean, nullable=False, default=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Promotion(db.Model):
    __tablename__ = 'promotions'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'code', name='uq_promotions_company_code'),
        db.CheckConstraint("discount_type IN ('PERCENT','FIXED')", name='ck_promotions_discount_type'),
        db.CheckConstraint('value > 0', name='ck_promotions_value_positive'),
        db.CheckConstraint('min_total >= 0', name='ck_promotions_min_total_nonnegative'),
        db.CheckConstraint(
            "discount_type != 'PERCENT' OR value <= 100",
            name='ck_promotions_percent_range',
        ),
        db.CheckConstraint("mechanic IN ('STANDARD','BUY_X_GET_Y','SECOND_PERCENT')", name='ck_promotions_mechanic'),
        db.CheckConstraint("scope IN ('ALL','PRODUCT','CATEGORY','BRAND')", name='ck_promotions_scope'),
        db.CheckConstraint('buy_qty > 0 AND reward_qty > 0 AND reward_percent >= 0 AND reward_percent <= 100', name='ck_promotions_rewards'),
        db.CheckConstraint('max_discount IS NULL OR max_discount >= 0', name='ck_promotions_max_discount'),
        db.CheckConstraint(
            'starts_at IS NULL OR ends_at IS NULL OR ends_at >= starts_at',
            name='ck_promotions_date_range',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    code = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    discount_type = db.Column(db.String(20), nullable=False, default='PERCENT')
    value = db.Column(db.Numeric(12, 2), nullable=False)
    min_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    mechanic = db.Column(db.String(30), nullable=False, default='STANDARD')
    scope = db.Column(db.String(20), nullable=False, default='ALL')
    target_product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True, index=True)
    target_category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True, index=True)
    target_brand = db.Column(db.String(100), nullable=True)
    buy_qty = db.Column(db.Numeric(14, 3), nullable=False, default=1)
    reward_qty = db.Column(db.Numeric(14, 3), nullable=False, default=1)
    reward_percent = db.Column(db.Numeric(7, 3), nullable=False, default=100)
    max_discount = db.Column(db.Numeric(12, 2), nullable=True)
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    target_product = db.relationship('Product', foreign_keys=[target_product_id])
    target_category = db.relationship('Category', foreign_keys=[target_category_id])

    def is_available(self, now=None, subtotal=None):
        now = now or utcnow()
        if not self.active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        if subtotal is not None and subtotal < (self.min_total or 0):
            return False
        return True
