from db import db
from datetime import datetime, timezone

class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    status = db.Column(db.String(50), default='Lead') 
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)

    sales = db.relationship('Sale', back_populates='client', lazy=True)
    interactions = db.relationship('Interaction', backref='client', lazy=True, cascade="all, delete-orphan")

    tasks = db.relationship('Task', backref='client', lazy=True, cascade="all, delete-orphan")

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