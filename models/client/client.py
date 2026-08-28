from db import db
from datetime import datetime, timezone

class Client(db.Model):
    __tablename__ = 'clients'
    __table_args__ = (
        db.CheckConstraint(
            'loyalty_points >= 0 AND loyalty_points <= 9999999999.9999',
            name='ck_clients_loyalty_points_range',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    status = db.Column(db.String(50), default='Lead') 
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    archived_at = db.Column(db.DateTime, nullable=True, index=True)

    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    price_list_id = db.Column(db.Integer, db.ForeignKey('price_lists.id'), nullable=True)
    credit_enabled = db.Column(db.Boolean, nullable=False, default=False)
    credit_limit = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payment_terms_days = db.Column(db.Integer, nullable=False, default=0)
    credit_hold = db.Column(db.Boolean, nullable=False, default=False)
    loyalty_points = db.Column(db.Numeric(14, 4), nullable=False, default=0)

    sales = db.relationship('Sale', back_populates='client', lazy=True)
    interactions = db.relationship('Interaction', backref='client', lazy=True, cascade="all, delete-orphan")

    tasks = db.relationship('Task', backref='client', lazy=True, cascade="all, delete-orphan")
    price_list = db.relationship('PriceList')

    def __repr__(self):
        return f'<Client {self.name}>'

class Interaction(db.Model):
    __tablename__ = 'interactions'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='Nota')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    user = db.relationship('User', backref='user_interactions')