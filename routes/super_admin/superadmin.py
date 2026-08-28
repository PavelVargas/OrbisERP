from services.time_utils import utcnow
import os
import logging
import hmac
from flask import Blueprint, abort, current_app, render_template, session, redirect, url_for, flash, request, send_file
from pathlib import Path
from models.user.user import User
from models.company.company import Company, GlobalAnnouncement, SuperadminLog # Importados
from models.divisas.divisas import ExchangeRate
from models.warehouse.warehouse import Warehouse
from db import db
from functools import wraps
from datetime import datetime, timedelta
from sqlalchemy import func

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


def cron_or_superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') == 'superadmin':
            return f(*args, **kwargs)
        configured = current_app.config.get('CRON_SECRET', '')
        supplied = request.headers.get('X-Orbis-Cron-Secret', '')
        if configured and len(configured) >= 32 and hmac.compare_digest(configured, supplied):
            return f(*args, **kwargs)
        abort(403)
    return decorated_function

# --- UTILIDADES DE INFRAESTRUCTURA ---

def get_dir_size(company_id):
    """Calcula el tamaño real en disco de los archivos de una empresa para Railway."""
    path = os.path.join('static', 'uploads', f'company_{company_id}')
    total_size = 0
    if os.path.exists(path):
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
    private_path = Path(current_app.config['STORAGE_ROOT']) / f'company_{company_id}'
    if private_path.exists():
        total_size += sum(item.stat().st_size for item in private_path.rglob('*') if item.is_file())
    return total_size


@superadmin_bp.get('/superadmin/receipts/<int:company_id>')
@superadmin_required
def download_receipt(company_id):
    company = Company.query.filter_by(id=company_id).first_or_404()
    stored = company.last_receipt_path or ''
    if stored.startswith('private:'):
        root = Path(current_app.config['STORAGE_ROOT']).resolve()
        target = (root / stored.removeprefix('private:')).resolve()
        expected_company_root = (root / f'company_{company.id}').resolve()
        if expected_company_root not in target.parents or not target.is_file():
            abort(404)
        return send_file(target, as_attachment=False, download_name=target.name)
    # Compatibility with receipts uploaded before private storage existed.
    legacy = (Path(current_app.static_folder).resolve() / stored).resolve()
    if Path(current_app.static_folder).resolve() not in legacy.parents or not legacy.is_file():
        abort(404)
    return send_file(legacy, as_attachment=False, download_name=legacy.name)

# --- RUTAS DEL DASHBOARD MAESTRO ---

@superadmin_bp.route('/superadmin/dashboard')
@superadmin_required
def admin_dashboard():
    # Limpieza de residuos de suplantaciones previas
    session.pop('company_id', None)
    session.pop('impersonating', None)
    session.pop('warehouse_id', None)

    companies = Company.query.all()
    total_users = User.query.count()
    ahora = utcnow()
    limite_vencimiento = ahora + timedelta(days=3)

    # --- LÓGICA DE INFRAESTRUCTURA REAL (RAILWAY) ---
    try:
        disk_limit_gb = float(os.getenv('TOTAL_DISK_LIMIT_GB', 0.5))
    except (ValueError, TypeError):
        disk_limit_gb = 0.5

    railway_limit_bytes = disk_limit_gb * 1024 * 1024 * 1024
    total_disk_mb_display = int(disk_limit_gb * 1024)

    raw_usage = db.session.query(func.sum(Company.current_storage_usage)).scalar() or 0
    total_used_bytes = float(raw_usage)

    total_used_mb = round(total_used_bytes / 1024 / 1024, 2)
    infra_perc = (total_used_bytes / railway_limit_bytes * 100) if railway_limit_bytes > 0 else 0

    # --- SEGMENTACIÓN Y ALERTAS ---
    plan_counts = {
        'BASIC': Company.query.filter_by(plan_name='BASIC').count(),
        'PRO': Company.query.filter_by(plan_name='PRO').count(),
        'ULTRA': Company.query.filter_by(plan_name='ULTRA').count()
    }

    critical_nodes = Company.query.filter(
        Company.expiration_date <= limite_vencimiento,
        Company.status == True
    ).all()

    # --- KPI FINANCIERO (MRR) ---
    # Ajusta estos valores a tus precios reales en RD$
    plan_prices = {
        'BASIC': 1500.0,
        'PRO': 3500.0,
        'ULTRA': 8000.0
    }
    total_mrr = sum(plan_counts[p] * plan_prices[p] for p in plan_prices)

    # --- ANUNCIO ACTIVO ---
    active_announcement = GlobalAnnouncement.query.filter_by(is_active=True).first()

    # LÓGICA DE DIVISA Y PREPARACIÓN DE EMPRESAS
    for company in companies:
        db_currency = ExchangeRate.query.filter_by(company_id=company.id, rate=1.0).first()
        if not db_currency:
            db_currency = ExchangeRate.query.filter_by(company_id=company.id).first()

        if db_currency:
            company.display_currency_code = db_currency.currency_code
            company.display_currency_symbol = db_currency.symbol
        else:
            company.display_currency_code = "N/A"
            company.display_currency_symbol = "—"

    return render_template('superadmin/dashboard.html', 
                           companies=companies, 
                           total_users=total_users,
                           total_used_mb=total_used_mb,
                           total_disk_mb=total_disk_mb_display,
                           infra_perc=int(infra_perc),
                           plan_counts=plan_counts,
                           critical_nodes=critical_nodes,
                           total_mrr=total_mrr,
                           active_announcement=active_announcement,
                           ahora=ahora)

@superadmin_bp.route('/superadmin/impersonate/<int:company_id>', methods=['POST'])
@superadmin_required
def impersonate(company_id):
    company = Company.query.get_or_404(company_id)
    
    # --- REGISTRO DE AUDITORÍA MASTER ---
    new_log = SuperadminLog(
        admin_id=session.get('user_id'),
        company_id=company.id,
        action="Impersonate",
        description=f"Acceso de soporte iniciado para el nodo {company.name}",
        ip_address=request.remote_addr
    )
    db.session.add(new_log)
    
    session.pop('selected_currency', None)
    session.pop('currency_symbol', None)
    
    session['company_id'] = company.id
    session['impersonating'] = True 
    
    db_exchange = ExchangeRate.query.filter_by(company_id=company.id, rate=1.0).first()
    if not db_exchange:
        db_exchange = ExchangeRate.query.filter_by(company_id=company.id).first()
    
    if db_exchange:
        session['selected_currency'] = db_exchange.currency_code
        session['currency_symbol'] = db_exchange.symbol 
    else:
        session['selected_currency'] = '???'
        session['currency_symbol'] = '?'

    w = Warehouse.query.filter_by(company_id=company.id).first()
    if w:
        session['warehouse_id'] = w.id
    
    db.session.commit() # Guardamos el log y los cambios
    flash(f'Soporte Técnico: Contexto {company.name} activado', 'info')
    return redirect(url_for('dashboard_bp.dashboard'))

# --- ACCIONES DE BROADCAST (ANUNCIOS GLOBALES) ---

@superadmin_bp.route('/superadmin/broadcast', methods=['POST'])
@superadmin_required
def create_broadcast():
    msg = request.form.get('message')
    alert_type = request.form.get('type', 'info')
    
    if msg:
        # Desactivamos anuncios previos antes de crear el nuevo
        GlobalAnnouncement.query.update({GlobalAnnouncement.is_active: False})
        
        new_ann = GlobalAnnouncement(message=msg, type=alert_type)
        db.session.add(new_ann)
        
        # Log de la acción
        db.session.add(SuperadminLog(
            admin_id=session.get('user_id'),
            action="Create Broadcast",
            description=f"Nuevo anuncio global: {msg[:50]}..."
        ))
        
        db.session.commit()
        flash("Anuncio global publicado exitosamente.", "success")
    return redirect(url_for('superadmin_bp.admin_dashboard'))

@superadmin_bp.route('/superadmin/broadcast/clear', methods=['POST'])
@superadmin_required
def clear_broadcast():
    GlobalAnnouncement.query.update({GlobalAnnouncement.is_active: False})
    db.session.commit()
    flash("Anuncios globales desactivados.", "info")
    return redirect(url_for('superadmin_bp.admin_dashboard'))

# --- ACCIONES DE CONTROL ---

@superadmin_bp.route('/superadmin/toggle_status/<int:id>', methods=['POST'])
@superadmin_required
def toggle_status(id):
    company = Company.query.get_or_404(id)
    company.status = not company.status
    
    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'),
        company_id=id,
        action="Toggle Status",
        description=f"Estado del nodo cambiado a {'Online' if company.status else 'Offline'}"
    ))
    
    db.session.commit()
    return redirect(url_for('superadmin_bp.admin_dashboard'))

@superadmin_bp.route('/superadmin/toggle_readonly/<int:id>', methods=['POST'])
@superadmin_required
def toggle_readonly(id):
    company = Company.query.get_or_404(id)
    company.is_readonly = not company.is_readonly
    
    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'),
        company_id=id,
        action="Toggle ReadOnly",
        description=f"Modo solo lectura: {company.is_readonly}"
    ))
    
    db.session.commit()
    estado = "SÓLO LECTURA" if company.is_readonly else "ACCESO TOTAL"
    flash(f"Nodo {company.name} puesto en modo {estado}", "info")
    return redirect(url_for('superadmin_bp.admin_dashboard'))

@superadmin_bp.route('/superadmin/refresh_storage/<int:id>', methods=['POST'])
@superadmin_required
def refresh_storage(id):
    company = Company.query.get_or_404(id)
    usage = get_dir_size(id)
    company.current_storage_usage = usage
    db.session.commit()
    flash(f"Almacenamiento actualizado para {company.name}", "success")
    return redirect(url_for('superadmin_bp.admin_dashboard'))

@superadmin_bp.route('/superadmin/delete_company/<int:id>', methods=['POST'])
@superadmin_required
def delete_company(id):
    company = Company.query.get_or_404(id)
    name = company.name
    
    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'),
        action="Delete Company",
        description=f"Nodo eliminado permanentemente: {name}"
    ))
    
    db.session.delete(company)
    db.session.commit()
    flash(f'Empresa {name} borrada permanentemente', 'danger')
    return redirect(url_for('superadmin_bp.admin_dashboard'))

# --- CRON ---

@superadmin_bp.post('/superadmin/cron/check-expirations')
@cron_or_superadmin_required
def cron_check_expirations():
    ahora = utcnow()
    expired_companies = Company.query.filter(
        Company.expiration_date < ahora,
        Company.status == True,
        (Company.grace_period_until == None) | (Company.grace_period_until < ahora)
    ).all()

    count = 0
    for c in expired_companies:
        c.status = False
        count += 1
    
    db.session.commit()
    return f"Cron ejecutado: {count} nodos suspendidos automáticamente.", 200

# --- PAGOS ---

@superadmin_bp.route('/superadmin/payments')
@superadmin_required
def view_payments():
    pending_payments = Company.query.filter(Company.receipt_status != 'NONE').order_by(Company.created_at.desc()).all()
    return render_template('superadmin/payments_management.html', payments=pending_payments)

@superadmin_bp.route('/superadmin/approve_payment/<int:id>', methods=['POST'])
@superadmin_required
def approve_payment(id):
    company = Company.query.get_or_404(id)
    ahora = utcnow()
    
    is_plan_change = company.requested_plan and company.requested_plan != company.plan_name
    
    if is_plan_change:
        company.plan_name = company.requested_plan
        company.expiration_date = ahora + timedelta(days=30)
        msg = f"Plan actualizado a {company.plan_name}."
    else:
        if company.expiration_date and company.expiration_date > ahora:
            company.expiration_date += timedelta(days=30)
        else:
            company.expiration_date = ahora + timedelta(days=30)
        msg = f"Suscripción extendida 30 días."

    limits = company.get_plan_limits()
    company.storage_limit = limits.get('storage_bytes', 524288000)

    company.requested_plan = None
    company.plan_status = 'ACTIVE'
    company.receipt_status = 'APPROVED'
    company.grace_period_until = None
    company.status = True 

    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'),
        company_id=id,
        action="Approve Payment",
        description=f"Pago aprobado. Plan: {company.plan_name}"
    ))
    
    db.session.commit()
    flash(msg, "success")
    return redirect(url_for('superadmin_bp.admin_dashboard'))

@superadmin_bp.route('/superadmin/renew_plan/<int:id>', methods=['POST'])
@superadmin_required
def renew_plan(id):
    company = Company.query.get_or_404(id)
    ahora = utcnow()
    
    if not company.expiration_date or company.expiration_date < ahora:
        company.expiration_date = ahora + timedelta(days=30)
    else:
        company.expiration_date += timedelta(days=30)
    
    company.status = True
    company.plan_status = 'ACTIVE'
    company.receipt_status = 'APPROVED'
    
    limits = company.get_plan_limits()
    company.storage_limit = limits.get('storage_bytes', 524288000)
    
    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'),
        company_id=id,
        action="Manual Renew",
        description="Renovación manual de 30 días ejecutada por superadmin"
    ))
    
    db.session.commit()
    flash(f'Plan de {company.name} renovado exitosamente.', 'success')
    return redirect(url_for('superadmin_bp.admin_dashboard'))
