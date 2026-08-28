from services.time_utils import utcnow
from db import db
from datetime import datetime

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(255)) 
    description = db.Column(db.Text)   
    created_at = db.Column(db.DateTime, default=utcnow)
    ip_address = db.Column(db.String(50))
    request_id = db.Column(db.String(64), nullable=True, index=True)
    endpoint = db.Column(db.String(150), nullable=True, index=True)
    entity_type = db.Column(db.String(80), nullable=True, index=True)
    entity_id = db.Column(db.String(80), nullable=True)
