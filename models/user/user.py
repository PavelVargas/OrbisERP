from services.time_utils import utcnow
import json
from datetime import datetime

from db import db
from permissions import ALL_PERMISSIONS, PROFILE_PRESETS
from werkzeug.security import check_password_hash, generate_password_hash

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    cedula = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(150), nullable=False, default="user")
    permissions = db.Column(db.Text, nullable=True)
    totp_secret = db.Column(db.String(64), nullable=True)
    two_factor_enabled = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    totp_recovery_codes = db.Column(db.Text, nullable=True)
    avatar_path = db.Column(db.String(255), nullable=True)
    email_verified_at = db.Column(db.DateTime, nullable=True, index=True)
    email_verification_sent_at = db.Column(db.DateTime, nullable=True)
    email_verification_code_hash = db.Column(db.String(64), nullable=True)
    email_verification_code_expires_at = db.Column(db.DateTime, nullable=True)
    email_verification_attempts = db.Column(db.Integer, nullable=False, default=0)
    terms_accepted_at = db.Column(db.DateTime, nullable=True)
    legal_version = db.Column(db.String(40), nullable=True)

    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    terminal_id = db.Column(db.Integer, db.ForeignKey('pos_terminals.id'), nullable=True)
    assigned_warehouse = db.relationship('Warehouse', backref='assigned_users')
    assigned_branch = db.relationship('Branch', backref='assigned_users')
    assigned_terminal = db.relationship('PosTerminal', backref='assigned_users')
    default_currency = db.Column(db.String(3), default='DOP', nullable=False)
    
    company_id = db.Column(
        db.Integer,
        db.ForeignKey('companies.id'),
        nullable=True
    )

    @property
    def email_verified(self):
        return self.email_verified_at is not None

    def mark_email_verified(self):
        self.email_verified_at = utcnow()

    def set_password(self, raw_password):
        """Store a strong one-way password hash."""
        self.password = generate_password_hash(raw_password)
        self.session_version = int(self.session_version or 0) + 1

    def check_password(self, raw_password):
        """Validate hashes and transparently support legacy plain-text rows."""
        if not raw_password or not self.password:
            return False
        if self.password.startswith(('scrypt:', 'pbkdf2:')):
            return check_password_hash(self.password, raw_password)
        return self.password == raw_password

    def permission_set(self):
        """Return effective permissions; NULL preserves access for legacy users."""
        if self.role in {'admin', 'superadmin'}:
            return set(ALL_PERMISSIONS)
        if self.permissions is None:
            return set(PROFILE_PRESETS['operational'])
        try:
            values = json.loads(self.permissions)
        except (TypeError, ValueError):
            values = []
        return {value for value in values if value in ALL_PERMISSIONS}

    def set_permissions(self, values):
        clean = sorted(set(values or ()) & ALL_PERMISSIONS)
        self.permissions = json.dumps(clean, separators=(',', ':'))

    def has_permission(self, permission):
        return permission in self.permission_set()

    def has_any_permission(self, *permissions):
        effective = self.permission_set()
        return any(permission in effective for permission in permissions)

    def __repr__(self):
        return f'<User {self.name} - {self.role}>'
