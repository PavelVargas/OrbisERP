from db import db
from datetime import datetime, timedelta

class GlobalAnnouncement(db.Model):
    """Anuncios que aparecen en todas las empresas (Broadcast)"""
    __tablename__ = 'global_announcements'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    type = db.Column(db.String(20), default='info') 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SuperadminLog(db.Model):
    """Registro de auditoría privado para acciones de soporte y cambios maestros"""
    __tablename__ = 'superadmin_logs'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    action = db.Column(db.String(255), nullable=False) 
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    
    # --- SISTEMA DE PLANES ---
    plan_name = db.Column(db.String(20), default='BASIC') # BASIC, PRO, ULTRA
    plan_status = db.Column(db.String(20), default='ACTIVE')
    requested_plan = db.Column(db.String(20), nullable=True)
    
    # --- CONTROL DE ACCESO Y SEGURIDAD ---
    status = db.Column(db.Boolean, default=True) 
    is_readonly = db.Column(db.Boolean, default=False)
    expiration_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- GESTIÓN DE ALMACENAMIENTO ---
    storage_limit = db.Column(db.BigInteger, default=524288000) 
    current_storage_usage = db.Column(db.BigInteger, default=0)

    # PAGOS Y GRACIA
    last_receipt_path = db.Column(db.String(255), nullable=True)
    receipt_status = db.Column(db.String(20), default='NONE') 
    grace_period_until = db.Column(db.DateTime, nullable=True)

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
        ahora = datetime.utcnow()
        if self.expiration_date and self.expiration_date > ahora:
            return True
        if self.grace_period_until and self.grace_period_until > ahora:
            return True
        return False

    def get_plan_limits(self):
        plans = {
            'BASIC': {
                'max_warehouses': 1, 
                'max_users': 2, 
                'max_monthly_invoices': 500,
                'storage_bytes': 524288000 # 500MB
            },
            'PRO': {
                'max_warehouses': 3, 
                'max_users': 10, 
                'max_monthly_invoices': 5000,
                'storage_bytes': 2147483648 # 2GB
            },
            'ULTRA': {
                'max_warehouses': 10, 
                'max_users': 100, 
                'max_monthly_invoices': 999999,
                'storage_bytes': 10737418240 # 10GB
            }
        }
        return plans.get(self.plan_name, plans['BASIC'])

    def get_current_month_usage(self):
        from models.sales.sales import Sale 
        ahora = datetime.utcnow()
        primer_dia_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        count = Sale.query.filter(
            Sale.company_id == self.id,
            Sale.created_at >= primer_dia_mes
        ).count()
        
        return count

    def __repr__(self):
        return f'<Company {self.name} | Plan: {self.plan_name}>'

SuperadminLog.target_company = db.relationship('Company', back_populates='support_logs')