from services.time_utils import utcnow
import os
import logging
import hmac
from decimal import Decimal
from uuid import uuid4
from flask import Blueprint, abort, current_app, render_template, session, redirect, url_for, flash, request, send_file
from pathlib import Path
from models.user.user import User
from models.company.company import Company, GlobalAnnouncement, SuperadminLog
from models.divisas.divisas import ExchangeRate
from models.warehouse.warehouse import Warehouse
from models.operations import BillingInvoice
from db import db
from functools import wraps
from datetime import timedelta
from sqlalchemy import func

logger = logging.getLogger(__name__)

superadmin_bp = Blueprint('superadmin_bp', __name__)

PLAN_PRICES = {
    'BASIC': Decimal('1500.00'),
    'PRO': Decimal('3500.00'),
    'ULTRA': Decimal('8000.00'),
}


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


def _clear_tenant_context():
    """Keep the platform owner independent from every tenant/company context."""
    for key in (
        'company_id', 'company_name', 'warehouse_id', 'branch_id', 'terminal_id',
        'impersonating', 'original_user_id', 'current_sale_id',
    ):
        session.pop(key, None)


@superadmin_bp.before_request
def isolate_master_context():
    """Every /superadmin page is a company-less master context.

    The impersonation endpoint starts clean and then explicitly selects a tenant.
    """
    if session.get('user_role') == 'superadmin' and request.endpoint != 'superadmin_bp.cron_check_expirations':
        _clear_tenant_context()


@superadmin_bp.context_processor
def inject_master_navigation_state():
    if session.get('user_role') != 'superadmin':
        return {'master_pending_count': 0}
    return {'master_pending_count': Company.query.filter_by(receipt_status='PENDING').count()}


# --- UTILIDADES DE INFRAESTRUCTURA ---

def get_dir_size(company_id):
    """Calcula el tamaño real en disco de los archivos de una empresa."""
    path = os.path.join('static', 'uploads', f'company_{company_id}')
    total_size = 0
    if os.path.exists(path):
        for dirpath, _dirnames, filenames in os.walk(path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if not os.path.islink(file_path):
                    total_size += os.path.getsize(file_path)
    private_path = Path(current_app.config['STORAGE_ROOT']) / f'company_{company_id}'
    if private_path.exists():
        total_size += sum(item.stat().st_size for item in private_path.rglob('*') if item.is_file())
    return total_size


def _company_admins(companies):
    ids = [company.id for company in companies]
    if not ids:
        return {}, {}
    counts = dict(
        db.session.query(User.company_id, func.count(User.id))
        .filter(User.company_id.in_(ids))
        .group_by(User.company_id)
        .all()
    )
    admins = {}
    rows = (
        User.query
        .filter(User.company_id.in_(ids), User.role == 'admin')
        .order_by(User.company_id.asc(), User.id.asc())
        .all()
    )
    for row in rows:
        admins.setdefault(row.company_id, row)
    return counts, admins


def _billing_totals(now):
    paid = func.upper(BillingInvoice.status) == 'PAID'
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.session.query(func.coalesce(func.sum(BillingInvoice.amount), 0)).filter(paid).scalar() or 0
    month = (
        db.session.query(func.coalesce(func.sum(BillingInvoice.amount), 0))
        .filter(paid, BillingInvoice.paid_at >= month_start)
        .scalar() or 0
    )
    return Decimal(str(total)), Decimal(str(month))


def _prepare_company_currency(companies):
    for company in companies:
        db_currency = ExchangeRate.query.filter_by(company_id=company.id, rate=1.0).first()
        if not db_currency:
            db_currency = ExchangeRate.query.filter_by(company_id=company.id).first()
        if db_currency:
            company.display_currency_code = db_currency.currency_code
            company.display_currency_symbol = db_currency.symbol
        else:
            company.display_currency_code = 'N/A'
            company.display_currency_symbol = '—'


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
    legacy = (Path(current_app.static_folder).resolve() / stored).resolve()
    if Path(current_app.static_folder).resolve() not in legacy.parents or not legacy.is_file():
        abort(404)
    return send_file(legacy, as_attachment=False, download_name=legacy.name)


# --- CENTRO MAESTRO ---

@superadmin_bp.route('/superadmin/dashboard')
@superadmin_required
def admin_dashboard():
    companies = Company.query.order_by(Company.created_at.desc(), Company.id.desc()).all()
    _prepare_company_currency(companies)
    total_users = User.query.filter(User.role != 'superadmin').count()
    now = utcnow()
    expiry_limit = now + timedelta(days=3)

    try:
        disk_limit_gb = float(os.getenv('TOTAL_DISK_LIMIT_GB', 0.5))
    except (ValueError, TypeError):
        disk_limit_gb = 0.5
    railway_limit_bytes = disk_limit_gb * 1024 * 1024 * 1024
    total_disk_mb = int(disk_limit_gb * 1024)
    raw_usage = db.session.query(func.sum(Company.current_storage_usage)).scalar() or 0
    total_used_bytes = float(raw_usage)
    total_used_mb = round(total_used_bytes / 1024 / 1024, 2)
    infra_perc = (total_used_bytes / railway_limit_bytes * 100) if railway_limit_bytes > 0 else 0

    plan_counts = {plan: Company.query.filter_by(plan_name=plan).count() for plan in PLAN_PRICES}
    total_mrr = sum(Decimal(plan_counts[plan]) * PLAN_PRICES[plan] for plan in PLAN_PRICES)
    critical_nodes = (
        Company.query
        .filter(Company.expiration_date.isnot(None), Company.expiration_date <= expiry_limit, Company.status.is_(True))
        .order_by(Company.expiration_date.asc())
        .all()
    )
    pending_count = Company.query.filter_by(receipt_status='PENDING').count()
    collected_total, collected_month = _billing_totals(now)
    recent_payments = (
        db.session.query(BillingInvoice, Company)
        .join(Company, BillingInvoice.company_id == Company.id)
        .filter(func.upper(BillingInvoice.status) == 'PAID')
        .order_by(BillingInvoice.paid_at.desc().nullslast(), BillingInvoice.created_at.desc())
        .limit(6)
        .all()
    )
    active_announcement = GlobalAnnouncement.query.filter_by(is_active=True).first()

    return render_template(
        'superadmin/dashboard.html',
        companies=companies,
        total_users=total_users,
        total_used_mb=total_used_mb,
        total_disk_mb=total_disk_mb,
        infra_perc=int(infra_perc),
        plan_counts=plan_counts,
        critical_nodes=critical_nodes,
        total_mrr=total_mrr,
        pending_payments=pending_count,
        collected_total=collected_total,
        collected_month=collected_month,
        recent_payments=recent_payments,
        active_announcement=active_announcement,
        ahora=now,
    )


@superadmin_bp.get('/superadmin/clients')
@superadmin_required
def clients():
    companies = Company.query.order_by(Company.created_at.desc(), Company.id.desc()).all()
    _prepare_company_currency(companies)
    user_counts, admins = _company_admins(companies)
    now = utcnow()
    return render_template(
        'superadmin/clients.html',
        companies=companies,
        user_counts=user_counts,
        admins=admins,
        plan_prices=PLAN_PRICES,
        ahora=now,
    )


@superadmin_bp.get('/superadmin/activity')
@superadmin_required
def activity():
    rows = (
        db.session.query(SuperadminLog, Company)
        .outerjoin(Company, SuperadminLog.company_id == Company.id)
        .order_by(SuperadminLog.created_at.desc(), SuperadminLog.id.desc())
        .limit(300)
        .all()
    )
    return render_template('superadmin/activity.html', rows=rows)


@superadmin_bp.route('/superadmin/impersonate/<int:company_id>', methods=['POST'])
@superadmin_required
def impersonate(company_id):
    company = Company.query.get_or_404(company_id)
    session['original_user_id'] = session.get('user_id')
    session['company_id'] = company.id
    session['company_name'] = company.name
    session['impersonating'] = True
    session.pop('selected_currency', None)
    session.pop('currency_symbol', None)

    db_exchange = ExchangeRate.query.filter_by(company_id=company.id, rate=1.0).first()
    if not db_exchange:
        db_exchange = ExchangeRate.query.filter_by(company_id=company.id).first()
    if db_exchange:
        session['selected_currency'] = db_exchange.currency_code
        session['currency_symbol'] = db_exchange.symbol
    else:
        session['selected_currency'] = 'DOP'
        session['currency_symbol'] = 'RD$'

    warehouse = Warehouse.query.filter_by(company_id=company.id).order_by(Warehouse.id.asc()).first()
    if warehouse:
        session['warehouse_id'] = warehouse.id

    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'),
        company_id=company.id,
        action='Impersonate',
        description=f'Acceso de soporte iniciado para {company.name}',
        ip_address=request.remote_addr,
    ))
    db.session.commit()
    flash(f'Modo soporte activo: {company.name}', 'info')
    return redirect(url_for('dashboard_bp.dashboard'))


# --- COMUNICACIÓN GLOBAL ---

@superadmin_bp.route('/superadmin/broadcast', methods=['POST'])
@superadmin_required
def create_broadcast():
    message = (request.form.get('message') or '').strip()
    alert_type = request.form.get('type', 'info')
    if alert_type not in {'info', 'warning', 'danger'}:
        alert_type = 'info'
    if message:
        GlobalAnnouncement.query.update({GlobalAnnouncement.is_active: False})
        db.session.add(GlobalAnnouncement(message=message[:500], type=alert_type))
        db.session.add(SuperadminLog(
            admin_id=session.get('user_id'),
            action='Create Broadcast',
            description=f'Anuncio global: {message[:100]}',
            ip_address=request.remote_addr,
        ))
        db.session.commit()
        flash('Anuncio global publicado.', 'success')
    return redirect(url_for('superadmin_bp.admin_dashboard'))


@superadmin_bp.route('/superadmin/broadcast/clear', methods=['POST'])
@superadmin_required
def clear_broadcast():
    GlobalAnnouncement.query.update({GlobalAnnouncement.is_active: False})
    db.session.commit()
    flash('Anuncio global desactivado.', 'info')
    return redirect(url_for('superadmin_bp.admin_dashboard'))


# --- CONTROL DE CLIENTES / TENANTS ---

def _clients_redirect():
    return redirect(url_for('superadmin_bp.clients'))


@superadmin_bp.route('/superadmin/toggle_status/<int:id>', methods=['POST'])
@superadmin_required
def toggle_status(id):
    company = Company.query.get_or_404(id)
    company.status = not company.status
    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'), company_id=id, action='Toggle Status',
        description=f"Estado cambiado a {'Activa' if company.status else 'Suspendida'}",
        ip_address=request.remote_addr,
    ))
    db.session.commit()
    flash(f'{company.name}: estado actualizado.', 'success')
    return _clients_redirect()


@superadmin_bp.route('/superadmin/toggle_readonly/<int:id>', methods=['POST'])
@superadmin_required
def toggle_readonly(id):
    company = Company.query.get_or_404(id)
    company.is_readonly = not company.is_readonly
    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'), company_id=id, action='Toggle ReadOnly',
        description=f'Modo solo lectura: {company.is_readonly}', ip_address=request.remote_addr,
    ))
    db.session.commit()
    flash(f"{company.name}: {'solo lectura' if company.is_readonly else 'acceso total'}.", 'info')
    return _clients_redirect()


@superadmin_bp.route('/superadmin/refresh_storage/<int:id>', methods=['POST'])
@superadmin_required
def refresh_storage(id):
    company = Company.query.get_or_404(id)
    company.current_storage_usage = get_dir_size(id)
    db.session.commit()
    flash(f'Almacenamiento actualizado para {company.name}.', 'success')
    return _clients_redirect()


@superadmin_bp.route('/superadmin/delete_company/<int:id>', methods=['POST'])
@superadmin_required
def delete_company(id):
    company = Company.query.get_or_404(id)
    name = company.name
    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'), action='Delete Company',
        description=f'Empresa eliminada permanentemente: {name}', ip_address=request.remote_addr,
    ))
    db.session.delete(company)
    db.session.commit()
    flash(f'Empresa {name} eliminada.', 'danger')
    return _clients_redirect()


# --- CRON ---

@superadmin_bp.post('/superadmin/cron/check-expirations')
@cron_or_superadmin_required
def cron_check_expirations():
    now = utcnow()
    expired_companies = Company.query.filter(
        Company.expiration_date < now,
        Company.status.is_(True),
        (Company.grace_period_until.is_(None)) | (Company.grace_period_until < now),
    ).all()
    for company in expired_companies:
        company.status = False
    db.session.commit()
    return f'Cron ejecutado: {len(expired_companies)} nodos suspendidos automáticamente.', 200


# --- PAGOS DE LA PLATAFORMA ---

@superadmin_bp.route('/superadmin/payments')
@superadmin_required
def view_payments():
    now = utcnow()
    pending = Company.query.filter_by(receipt_status='PENDING').order_by(Company.id.desc()).all()
    history = (
        db.session.query(BillingInvoice, Company)
        .join(Company, BillingInvoice.company_id == Company.id)
        .order_by(BillingInvoice.paid_at.desc().nullslast(), BillingInvoice.created_at.desc())
        .limit(250)
        .all()
    )
    collected_total, collected_month = _billing_totals(now)
    paid_count = BillingInvoice.query.filter(func.upper(BillingInvoice.status) == 'PAID').count()
    return render_template(
        'superadmin/payments_management.html',
        pending=pending,
        history=history,
        plan_prices=PLAN_PRICES,
        collected_total=collected_total,
        collected_month=collected_month,
        paid_count=paid_count,
    )


@superadmin_bp.route('/superadmin/approve_payment/<int:id>', methods=['POST'])
@superadmin_required
def approve_payment(id):
    company = Company.query.filter_by(id=id).with_for_update().first_or_404()
    if company.receipt_status != 'PENDING':
        flash('Este comprobante ya fue procesado o no está pendiente.', 'warning')
        return redirect(url_for('superadmin_bp.view_payments'))

    now = utcnow()
    requested_plan = (company.requested_plan or company.plan_name or 'BASIC').upper()
    if requested_plan not in PLAN_PRICES:
        requested_plan = 'BASIC'
    previous_expiration = company.expiration_date
    is_plan_change = bool(company.requested_plan and company.requested_plan != company.plan_name)

    company.plan_name = requested_plan
    if is_plan_change or not previous_expiration or previous_expiration <= now:
        company.expiration_date = now + timedelta(days=30)
    else:
        company.expiration_date = previous_expiration + timedelta(days=30)

    company.storage_limit = company.get_plan_limits().get('storage_bytes', 524288000)
    company.requested_plan = None
    company.plan_status = 'ACTIVE'
    company.receipt_status = 'APPROVED'
    company.grace_period_until = None
    company.status = True
    company.is_readonly = False

    amount = PLAN_PRICES[requested_plan]
    invoice = BillingInvoice(
        company_id=company.id,
        external_id=f'manual-{company.id}-{uuid4().hex}',
        provider='manual_receipt',
        status='PAID',
        plan_name=requested_plan,
        amount=amount,
        currency='DOP',
        period_start=previous_expiration if previous_expiration and previous_expiration > now else now,
        period_end=company.expiration_date,
        paid_at=now,
    )
    db.session.add(invoice)
    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'),
        company_id=id,
        action='Approve Payment',
        description=f'Pago aprobado · {requested_plan} · RD$ {amount:,.2f}',
        ip_address=request.remote_addr,
    ))
    db.session.commit()
    flash(f'Pago de {company.name} registrado y suscripción actualizada.', 'success')
    return redirect(url_for('superadmin_bp.view_payments'))


@superadmin_bp.route('/superadmin/renew_plan/<int:id>', methods=['POST'])
@superadmin_required
def renew_plan(id):
    company = Company.query.get_or_404(id)
    now = utcnow()
    if not company.expiration_date or company.expiration_date < now:
        company.expiration_date = now + timedelta(days=30)
    else:
        company.expiration_date += timedelta(days=30)
    company.status = True
    company.plan_status = 'ACTIVE'
    company.is_readonly = False
    company.storage_limit = company.get_plan_limits().get('storage_bytes', 524288000)
    db.session.add(SuperadminLog(
        admin_id=session.get('user_id'), company_id=id, action='Manual Renew',
        description='Renovación administrativa de 30 días (sin registrar cobro)',
        ip_address=request.remote_addr,
    ))
    db.session.commit()
    flash(f'Plan de {company.name} renovado 30 días. No se registró como pago.', 'success')
    return _clients_redirect()
