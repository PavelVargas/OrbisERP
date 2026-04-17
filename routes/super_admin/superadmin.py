from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from models.user.user import User
from models.company.company import Company
from models.divisas.divisas import ExchangeRate
from models.warehouse.warehouse import Warehouse
from db import db
from functools import wraps
from datetime import datetime, timedelta
import logging

# Configuración de logs para rastrear cambios de contexto
logger = logging.getLogger(__name__)

superadmin_bp = Blueprint('superadmin_bp', __name__)

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'superadmin':
            flash('Acceso no autorizado', 'danger')
            return redirect(url_for('login_bp.login'))
        return f(*args, **kwargs)
    return decorated_function

@superadmin_bp.route('/superadmin/dashboard')
@superadmin_required
def admin_dashboard():
    # Limpieza de residuos de suplantaciones previas
    session.pop('company_id', None)
    session.pop('impersonating', None)
    session.pop('warehouse_id', None)

    companies = Company.query.all()
    total_users = User.query.count()

    # LÓGICA DE DIVISA BASADA ESTRICTAMENTE EN DB
    for company in companies:
        # 1. Intentamos buscar la moneda base (rate 1.0)
        db_currency = ExchangeRate.query.filter_by(company_id=company.id, rate=1.0).first()
        
        # 2. Si no hay 1.0 (como en tu imagen), tomamos la primera disponible para ese nodo
        if not db_currency:
            db_currency = ExchangeRate.query.filter_by(company_id=company.id).first()

        if db_currency:
            company.display_currency_code = db_currency.currency_code
            company.display_currency_symbol = db_currency.symbol
        else:
            # Fallback visual solo si la tabla está vacía para este ID
            company.display_currency_code = "N/A"
            company.display_currency_symbol = "—"

    return render_template('superadmin/dashboard.html', 
                           companies=companies, 
                           total_users=total_users)

@superadmin_bp.route('/superadmin/impersonate/<int:company_id>')
@superadmin_required
def impersonate(company_id):
    company = Company.query.get_or_404(company_id)
    
    # Limpieza total de sesión antes de entrar al nodo
    session.pop('selected_currency', None)
    session.pop('currency_symbol', None)
    
    # Establecer contexto de empresa
    session['company_id'] = company.id
    session['impersonating'] = True 
    
    # LEALTAD A LA BASE DE DATOS (Sincronización con imagen SQL)
    # Buscamos la moneda que el cliente tiene registrada, sin importar el rate
    db_exchange = ExchangeRate.query.filter_by(company_id=company.id, rate=1.0).first()
    
    if not db_exchange:
        # Si no hay base 1.0, agarramos la primera fila que exista (EUR o USD según tu tabla)
        db_exchange = ExchangeRate.query.filter_by(company_id=company.id).first()
    
    if db_exchange:
        session['selected_currency'] = db_exchange.currency_code
        session['currency_symbol'] = db_exchange.symbol 
        logger.info(f"Soporte: Accediendo a {company.name} en moneda: {db_exchange.currency_code}")
    else:
        # Si la empresa no tiene NADA en la tabla divisas, avisamos
        flash(f'Advertencia: El nodo {company.name} no tiene divisas configuradas en DB.', 'warning')
        session['selected_currency'] = '???'
        session['currency_symbol'] = '?'

    # Asignar almacén del nodo
    w = Warehouse.query.filter_by(company_id=company.id).first()
    if w:
        session['warehouse_id'] = w.id
    
    flash(f'Soporte Técnico: Contexto {company.name} activado ({session.get("selected_currency")})', 'info')
    return redirect(url_for('dashboard_bp.dashboard'))

@superadmin_bp.route('/superadmin/toggle_status/<int:id>', methods=['POST'])
@superadmin_required
def toggle_status(id):
    company = Company.query.get_or_404(id)
    company.status = not company.status
    db.session.commit()
    return redirect(url_for('superadmin_bp.admin_dashboard'))

@superadmin_bp.route('/superadmin/delete_company/<int:id>', methods=['POST'])
@superadmin_required
def delete_company(id):
    company = Company.query.get_or_404(id)
    db.session.delete(company)
    db.session.commit()
    flash(f'Empresa {company.name} borrada permanentemente', 'danger')
    return redirect(url_for('superadmin_bp.admin_dashboard'))

@superadmin_bp.route('/superadmin/payments')
@superadmin_required
def view_payments():
    pending_payments = Company.query.filter(Company.receipt_status != 'NONE').order_by(Company.created_at.desc()).all()
    return render_template('superadmin/payments_management.html', payments=pending_payments)

@superadmin_bp.route('/superadmin/approve_payment/<int:id>', methods=['POST'])
@superadmin_required
def approve_payment(id):
    company = Company.query.get_or_404(id)
    ahora = datetime.utcnow()
    
    is_plan_change = company.requested_plan and company.requested_plan != company.plan_name
    
    if is_plan_change:
        company.plan_name = company.requested_plan
        company.expiration_date = ahora + timedelta(days=30)
        msg = f"Plan actualizado a {company.plan_name}. 30 días iniciados."
    else:
        if company.expiration_date and company.expiration_date > ahora:
            company.expiration_date += timedelta(days=30)
        else:
            company.expiration_date = ahora + timedelta(days=30)
        msg = f"Suscripción {company.plan_name} extendida por 30 días."

    company.requested_plan = None
    company.plan_status = 'ACTIVE'
    company.receipt_status = 'APPROVED'
    company.grace_period_until = None
    company.status = True 
    
    db.session.commit()
    
    flash(msg, "success")
    return redirect(url_for('superadmin_bp.admin_dashboard'))

@superadmin_bp.route('/superadmin/renew_plan/<int:id>', methods=['POST'])
@superadmin_required
def renew_plan(id):
    company = Company.query.get_or_404(id)
    ahora = datetime.utcnow()
    
    if not company.expiration_date or company.expiration_date < ahora:
        company.expiration_date = ahora + timedelta(days=30)
    else:
        company.expiration_date += timedelta(days=30)
    
    company.status = True
    company.plan_status = 'ACTIVE'
    company.receipt_status = 'APPROVED'
    
    db.session.commit()
    
    flash(f'Plan de {company.name} renovado exitosamente por 30 días.', 'success')
    return redirect(url_for('superadmin_bp.admin_dashboard'))