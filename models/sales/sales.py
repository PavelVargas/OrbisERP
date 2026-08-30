from services.time_utils import utcnow
from db import db
from datetime import datetime
from sqlalchemy import CheckConstraint, Numeric, ForeignKey

class Sale(db.Model):
    __tablename__ = 'sales'
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_sales_subtotal_nonnegative"),
        CheckConstraint("itbis >= 0", name="ck_sales_itbis_nonnegative"),
        CheckConstraint("total >= 0", name="ck_sales_total_nonnegative"),
        CheckConstraint("amount_paid >= 0", name="ck_sales_paid_nonnegative"),
        CheckConstraint("balance >= 0", name="ck_sales_balance_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="ck_sales_discount_nonnegative"),
        CheckConstraint("cash_received IS NULL OR cash_received >= 0", name="ck_sales_cash_received_nonnegative"),
        CheckConstraint("cash_change >= 0", name="ck_sales_cash_change_nonnegative"),
        CheckConstraint(
            "status IN ('DRAFT','PENDING','QUOTATION','LAYAWAY','COMPLETED','CANCELLED')",
            name="ck_sales_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), nullable=True)

    subtotal = db.Column(Numeric(10,2), default=0)
    itbis = db.Column(Numeric(10,2), default=0)
    total = db.Column(Numeric(10,2), default=0)

    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)
    client_id = db.Column(db.Integer, ForeignKey('clients.id'), nullable=True)
    company_id = db.Column(db.Integer, ForeignKey('companies.id'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    terminal_id = db.Column(db.Integer, db.ForeignKey('pos_terminals.id'), nullable=True, index=True)
    price_list_id = db.Column(db.Integer, db.ForeignKey('price_lists.id'), nullable=True, index=True)

    status = db.Column(db.String(20), default='PENDING')
    created_at = db.Column(db.DateTime, default=utcnow)
    quote_valid_until = db.Column(db.Date, nullable=True)
    quote_notes = db.Column(db.String(500), nullable=True)
    promotion_id = db.Column(db.Integer, db.ForeignKey('promotions.id'), nullable=True)
    discount_amount = db.Column(Numeric(10,2), nullable=False, default=0)

    user = db.relationship('User', backref='sales_made')
    promotion = db.relationship('Promotion')
    branch = db.relationship('Branch')
    terminal = db.relationship('PosTerminal')
    price_list = db.relationship('PriceList')

    client = db.relationship(
        'Client',
        back_populates='sales'
    )

    items = db.relationship(
        'SaleItem',
        backref='sale',
        cascade='all, delete-orphan'
    )
    
    payment_method = db.Column(db.String(20), default='CASH')
    amount_paid = db.Column(Numeric(10,2), default=0)
    balance = db.Column(Numeric(10,2), default=0)
    # Cash drawer audit data. ``amount_paid`` remains the amount applied to the
    # sale; these fields preserve what the customer physically handed over and
    # the change returned by the cashier.
    cash_received = db.Column(Numeric(12,2), nullable=True)
    cash_change = db.Column(Numeric(12,2), nullable=False, default=0)

    @property
    def warehouse_names(self):
        """Return the real warehouse names recorded on this sale's line items."""
        names = []
        seen = set()
        for item in self.items or []:
            warehouse = getattr(item, 'warehouse', None)
            if not warehouse or warehouse.id in seen:
                continue
            seen.add(warehouse.id)
            names.append(warehouse.name)
        return names

    @property
    def warehouse_display(self):
        """Human-readable origin for list/detail views without inventing a default warehouse."""
        names = self.warehouse_names
        if not names:
            return 'Sin almacén registrado'
        if len(names) == 1:
            return names[0]
        return f'{len(names)} almacenes'

    def __repr__(self):
        return f'<Sale #{self.id} - {self.total} ({self.status})>'
