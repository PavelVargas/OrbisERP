from services.time_utils import utcnow
from db import db
from datetime import datetime, timedelta


PLAN_LIMITS = {
    'BASIC': {
        'max_warehouses': 1,
        'max_users': 2,
        'max_monthly_invoices': 500,
        'storage_bytes': 524288000,
    },
    'PRO': {
        'max_warehouses': 3,
        'max_users': 10,
        'max_monthly_invoices': 5000,
        'storage_bytes': 2147483648,
    },
    'ULTRA': {
        'max_warehouses': 10,
        'max_users': 100,
        'max_monthly_invoices': 999999,
        'storage_bytes': 10737418240,
    },
}

class GlobalAnnouncement(db.Model):
    """Anuncios que aparecen en todas las empresas (Broadcast)"""
    __tablename__ = 'global_announcements'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    type = db.Column(db.String(20), default='info') 
    created_at = db.Column(db.DateTime, default=utcnow)

class SuperadminLog(db.Model):
    """Registro de auditoría privado para acciones de soporte y cambios maestros"""
    __tablename__ = 'superadmin_logs'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    action = db.Column(db.String(255), nullable=False) 
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    admin_user = db.relationship('User', foreign_keys=[admin_id])
    target_company = db.relationship('Company', foreign_keys=[company_id])


# --- MODELO ORIGINAL DE EMPRESA ---

class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    rnc = db.Column(db.String(20), unique=True, nullable=True)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    logo = db.Column(db.String(255), nullable=True)

    # CONFIGURACIÓN FISCAL
    tax_name = db.Column(db.String(10), default='ITBIS') 
    tax_percent = db.Column(db.Numeric(5, 2), default=18.00) 
    currency_symbol = db.Column(db.String(10), default='RD$')
    invoice_footer = db.Column(db.Text, nullable=True)
    fiscal_mode = db.Column(db.String(20), nullable=False, default='disabled')
    fiscal_disclaimer = db.Column(db.String(180), nullable=False, default='DOCUMENTO NO FISCAL')
    
    # --- SISTEMA DE PLANES ---
    plan_name = db.Column(db.String(20), default='BASIC') # BASIC, PRO, ULTRA
    plan_status = db.Column(db.String(20), default='ACTIVE')
    requested_plan = db.Column(db.String(20), nullable=True)
    
    # --- CONTROL DE ACCESO Y SEGURIDAD ---
    status = db.Column(db.Boolean, default=True) 
    is_readonly = db.Column(db.Boolean, default=False)
    expiration_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    # --- GESTIÓN DE ALMACENAMIENTO ---
    storage_limit = db.Column(db.BigInteger, default=524288000) 
    current_storage_usage = db.Column(db.BigInteger, default=0)

    # PAGOS Y GRACIA
    last_receipt_path = db.Column(db.String(255), nullable=True)
    receipt_status = db.Column(db.String(20), default='NONE') 
    grace_period_until = db.Column(db.DateTime, nullable=True)
    billing_provider = db.Column(db.String(40), nullable=True)
    billing_customer_id = db.Column(db.String(120), nullable=True)
    billing_subscription_id = db.Column(db.String(120), nullable=True)
    cancel_at_period_end = db.Column(db.Boolean, default=False, nullable=False)
    onboarding_completed = db.Column(db.Boolean, default=False, nullable=False)

    # RELACIONES
    users_list = db.relationship('User', backref='company', lazy=True)
    products_list = db.relationship('Product', backref='company', lazy=True)
    sales_list = db.relationship('Sale', backref='company', lazy=True)
    
    # NUEVA RELACIÓN: Para ver los logs de soporte desde la empresa
    support_logs = db.relationship('SuperadminLog', back_populates='target_company', lazy=True)

    @property
    def is_active(self):
        if not self.status: 
            return False
        ahora = utcnow()
        if self.expiration_date and self.expiration_date > ahora:
            return True
        if self.grace_period_until and self.grace_period_until > ahora:
            return True
        return False

    def get_plan_limits(self):
        # Return a copy so callers cannot accidentally mutate the shared commercial contract.
        return dict(PLAN_LIMITS.get(self.plan_name, PLAN_LIMITS['BASIC']))

    def get_current_month_usage(self):
        from models.sales.sales import Sale 
        ahora = utcnow()
        primer_dia_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        count = Sale.query.filter(
            Sale.company_id == self.id,
            Sale.created_at >= primer_dia_mes,
            Sale.status == 'COMPLETED',
        ).count()
        
        return count

    def __repr__(self):
        return f'<Company {self.name} | Plan: {self.plan_name}>'

