from db import db
from datetime import datetime
from sqlalchemy import Numeric, ForeignKey

class Sale(db.Model):
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), nullable=True)

    subtotal = db.Column(Numeric(10,2), default=0)
    itbis = db.Column(Numeric(10,2), default=0)
    total = db.Column(Numeric(10,2), default=0)

    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)
    client_id = db.Column(db.Integer, ForeignKey('clients.id'), nullable=True)
    company_id = db.Column(db.Integer, ForeignKey('companies.id'), nullable=True)

    status = db.Column(db.String(20), default='PENDING')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='sales_made')

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

    def __repr__(self):
        return f'<Sale #{self.id} - {self.total} ({self.status})>'
