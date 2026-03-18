from db import db
from datetime import datetime

class CashClosing(db.Model):
    __tablename__ = 'cash_closings'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    opening_date = db.Column(db.DateTime, nullable=False) 
    closing_date = db.Column(db.DateTime, default=datetime.utcnow) 
    
    system_amount = db.Column(db.Numeric(12, 2), nullable=False)
    reported_amount = db.Column(db.Numeric(12, 2), nullable=False)
    difference = db.Column(db.Numeric(12, 2), nullable=False) 
    
    notes = db.Column(db.Text, nullable=True)

    user = db.relationship('User', backref='closings')