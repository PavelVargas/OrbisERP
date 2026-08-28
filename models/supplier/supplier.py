from services.time_utils import utcnow
from datetime import datetime
from db import db

class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    
    # Nuevo: Identificador de empresa
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow)
    archived_at = db.Column(db.DateTime, nullable=True, index=True)

    def __repr__(self):
        return f'<Supplier {self.name}>'
