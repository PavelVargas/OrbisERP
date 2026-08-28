from services.time_utils import utcnow
import csv
import hashlib
import io
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, inspect, or_, text
from sqlalchemy.exc import SQLAlchemyError

from db import db
from models.auditoria.auditoria import AuditLog
from models.operations import OperationJob, UserSession
from models.stock_transfer.stock_transfer import StockTransfer
from models.user.user import User
from services.csv_security import safe_csv_row


governance_bp = Blueprint('governance_bp', __name__, url_prefix='/governance')

AUDIT_ACTION_LABELS = {
    'SALE_RETURN': 'Devolución de venta',
    'CUSTOMER_PAYMENT': 'Cobro registrado',
    'SUPPLIER_BILL': 'Cuenta por pagar creada',
    'SUPPLIER_PAYMENT': 'Pago a proveedor registrado',
    'EXPENSE': 'Gasto registrado',
    'INVENTORY_COUNT_APPROVED': 'Conteo de inventario aprobado',
    'TWO_FACTOR_ENABLED': 'Autenticación en dos pasos activada',
    'TWO_FACTOR_DISABLED': 'Autenticación en dos pasos desactivada',
    'TWO_FACTOR_RECOVERY_REGENERATED': 'Códigos de recuperación regenerados',
    'USER_PERMISSIONS_UPDATED': 'Permisos de usuario actualizados',
}

AUDIT_ENDPOINT_LABELS = {
    'sales_bp.create_sale': 'Venta creada o actualizada',
    'sales_bp.quote_convert': 'Cotización convertida a venta',
    'crm_bp.add_interaction': 'Actividad CRM registrada',
    'crm_bp.update_status': 'Fase comercial actualizada',
    'crm_bp.add_task': 'Tarea CRM creada',
    'crm_bp.complete_task': 'Tarea CRM completada',
    'workspace_bp.document_upload': 'Documento subido',
    'workspace_bp.document_update': 'Documento actualizado',
    'workspace_bp.document_delete': 'Documento enviado a papelera',
    'workspace_bp.restore_document': 'Documento restaurado',
    'workspace_bp.purge_document': 'Documento eliminado definitivamente',
    'operations_bp.onboarding': 'Configuración inicial actualizada',
    'retail_bp.settings_update': 'Retail avanzado actualizado',
    'company_bp.settings': 'Datos de empresa actualizados',
    'workspace_bp.notification_rules': 'Reglas de alertas actualizadas',
    'perfil_bp.perfil': 'Perfil personal actualizado',
    'login_bp.logout': 'Sesión cerrada',
}


def _audit_action_label(raw):
    raw = (raw or '').strip()
    if raw in AUDIT_ACTION_LABELS:
        return AUDIT_ACTION_LABELS[raw]
    method = ''
    endpoint = ''
    if raw.startswith('HTTP_'):
        prefix, _, endpoint = raw.partition(':')
        method = prefix.replace('HTTP_', '')
    if endpoint:
        label = AUDIT_ENDPOINT_LABELS.get(endpoint)
        if not label:
            name = endpoint.split('.')[-1].replace('_', ' ').strip()
            label = name[:1].upper() + name[1:] if name else 'Actividad del sistema'
        return f'{label} · {method}' if method else label
    label = raw.replace('_', ' ').replace(':', ' · ').strip().title()
    return label or 'Actividad del sistema'

def _audit_presentation(row):
    raw = (row.action or '').strip()
    endpoint = (row.endpoint or '').strip()
    label = AUDIT_ACTION_LABELS.get(raw) or AUDIT_ENDPOINT_LABELS.get(endpoint)
    method = None
    if raw.startswith('HTTP_'):
        prefix, _, _endpoint = raw.partition(':')
        method = prefix.replace('HTTP_', '')
        if not endpoint:
            endpoint = _endpoint
    if not label:
        if endpoint:
            action_name = endpoint.split('.')[-1].replace('_', ' ').strip()
            label = action_name[:1].upper() + action_name[1:] if action_name else 'Actividad del sistema'
        else:
            label = raw.replace('_', ' ').replace(':', ' · ').strip().title() or 'Actividad del sistema'
    haystack = f'{raw} {endpoint}'.lower()
    if any(token in haystack for token in ('security', 'login', 'logout', 'session', 'password', 'two_factor', 'user')):
        category, icon = 'Seguridad', 'bi-shield-check'
    elif any(token in haystack for token in ('sale', 'cash', 'receivable', 'payment')):
        category, icon = 'Ventas y caja', 'bi-receipt'
    elif any(token in haystack for token in ('product', 'stock', 'warehouse', 'transfer', 'inventory')):
        category, icon = 'Inventario', 'bi-box-seam'
    elif any(token in haystack for token in ('purchase', 'supplier', 'payable', 'expense')):
        category, icon = 'Compras y gastos', 'bi-bag-check'
    elif any(token in haystack for token in ('crm', 'client')):
        category, icon = 'CRM', 'bi-people'
    elif 'document' in haystack:
        category, icon = 'Documentos', 'bi-folder2-open'
    else:
        category, icon = 'Sistema', 'bi-activity'
    description = (row.description or '').strip()
    generic_http = bool(method and description.upper().startswith(f'{method} '))
    if generic_http:
        summary = f'{label}. La solicitud se procesó correctamente.'
    elif description:
        summary = description
    else:
        summary = f'{label}. El evento no incluyó información adicional.'
    return {'label': label, 'category': category, 'icon': icon, 'method': method, 'summary': summary}



def _identity():
    company_id, user_id = session.get('company_id'), session.get('user_id')
    if not company_id or not user_id:
        abort(401)
    return int(company_id), int(user_id)


def _page_size():
    return min(max(request.args.get('per_page', 25, type=int) or 25, 10), 100)


def _integrity_checks(company_id):
    statements = [
        ('negative-stock', 'Stock negativo', 'critical', '''
            SELECT COUNT(*) FROM warehouse_stock
            WHERE company_id = :company_id AND quantity < 0
        '''),
        ('duplicate-stock', 'Stock duplicado', 'critical', '''
            SELECT COUNT(*) FROM (
                SELECT warehouse_id, product_id FROM warehouse_stock
                WHERE company_id = :company_id
                GROUP BY warehouse_id, product_id HAVING COUNT(*) > 1
            ) duplicates
        '''),
        ('location-overflow', 'Ubicaciones sobreasignadas', 'critical', '''
            SELECT COUNT(*) FROM (
                SELECT ws.warehouse_id, ws.product_id, ws.quantity, COALESCE(SUM(ls.quantity), 0) allocated
                FROM warehouse_stock ws
                LEFT JOIN warehouse_locations wl ON wl.warehouse_id = ws.warehouse_id AND wl.company_id = ws.company_id
                LEFT JOIN location_stock ls ON ls.location_id = wl.id AND ls.product_id = ws.product_id AND ls.company_id = ws.company_id
                WHERE ws.company_id = :company_id
                GROUP BY ws.warehouse_id, ws.product_id, ws.quantity
                HAVING COALESCE(SUM(ls.quantity), 0) > ws.quantity
            ) inconsistent
        '''),
        ('invalid-sales', 'Ventas con totales inválidos', 'critical', '''
            SELECT COUNT(*) FROM sales
            WHERE company_id = :company_id
              AND (total < 0 OR subtotal < 0 OR itbis < 0 OR amount_paid < 0 OR balance < 0)
        '''),
        ('payment-overflow', 'Pagos por encima del balance', 'critical', '''
            SELECT COUNT(*) FROM supplier_bills
            WHERE company_id = :company_id AND (paid_amount < 0 OR paid_amount > amount)
        '''),
        ('stale-transfers', 'Transferencias pendientes por más de 7 días', 'warning', '''
            SELECT COUNT(*) FROM stock_transfers
            WHERE company_id = :company_id AND status = 'PENDING'
              AND created_at < (CURRENT_TIMESTAMP - INTERVAL '7 days')
        '''),
        ('failed-jobs', 'Procesos fallidos recientes', 'warning', '''
            SELECT COUNT(*) FROM operation_jobs
            WHERE company_id = :company_id AND status = 'FAILED'
              AND created_at >= (CURRENT_TIMESTAMP - INTERVAL '30 days')
        '''),
    ]
    results = []
    for key, label, severity, statement in statements:
        try:
            count = int(db.session.execute(text(statement), {'company_id': company_id}).scalar_one())
            results.append({'key': key, 'label': label, 'severity': severity, 'count': count, 'available': True})
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Integrity check failed: %s', key)
            results.append({'key': key, 'label': label, 'severity': severity, 'count': None, 'available': False})
    return results


@governance_bp.get('/integrity')
def integrity_center():
    company_id, user_id = _identity()
    checks = _integrity_checks(company_id)
    stale = StockTransfer.query.filter(
        StockTransfer.company_id == company_id,
        StockTransfer.status == 'PENDING',
        StockTransfer.created_at < utcnow() - timedelta(days=7),
    ).order_by(StockTransfer.created_at.asc()).limit(25).all()
    healthy = all(item['available'] and item['count'] == 0 for item in checks)
    return render_template(
        'governance/integrity.html', user=db.session.get(User, user_id), checks=checks,
        healthy=healthy, stale_transfers=stale, checked_at=utcnow(),
    )


def _audit_query(company_id):
    query = AuditLog.query.filter(AuditLog.company_id == company_id)
    action = (request.args.get('action') or '').strip()
    endpoint = (request.args.get('audit_endpoint') or request.args.get('endpoint') or '').strip()
    search = (request.args.get('q') or '').strip()
    user_id = request.args.get('user_id', type=int)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    if action:
        query = query.filter(AuditLog.action.ilike(f'%{action}%'))
    if endpoint:
        query = query.filter(AuditLog.endpoint.ilike(f'%{endpoint}%'))
    if search:
        query = query.filter(or_(AuditLog.description.ilike(f'%{search}%'), AuditLog.request_id.ilike(f'%{search}%')))
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    try:
        if date_from:
            query = query.filter(AuditLog.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        if date_to:
            query = query.filter(AuditLog.created_at < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        pass
    return query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


def _audit_schema_columns():
    try:
        return {column['name'] for column in inspect(db.engine).get_columns('audit_logs')}
    except Exception:
        current_app.logger.exception('No se pudo inspeccionar el esquema de audit_logs')
        return set()


def _legacy_audit_payload(company_id):
    """Build a readable audit feed without selecting optional governance columns.

    This keeps the audit screen usable while an installation is still on the
    legacy audit_logs shape. It deliberately uses only the columns that existed
    before the governance expansion.
    """
    page = max(request.args.get('page', 1, type=int) or 1, 1)
    per_page = _page_size()
    search = (request.args.get('q') or '').strip()
    action = (request.args.get('action') or '').strip()
    user_filter = request.args.get('user_id', type=int)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()

    query = db.session.query(
        AuditLog.id.label('id'),
        AuditLog.user_id.label('user_id'),
        AuditLog.action.label('action'),
        AuditLog.description.label('description'),
        AuditLog.created_at.label('created_at'),
        AuditLog.ip_address.label('ip_address'),
    ).filter(AuditLog.company_id == company_id)
    if action:
        query = query.filter(AuditLog.action.ilike(f'%{action}%'))
    if search:
        query = query.filter(AuditLog.description.ilike(f'%{search}%'))
    if user_filter:
        query = query.filter(AuditLog.user_id == user_filter)
    try:
        if date_from:
            query = query.filter(AuditLog.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        if date_to:
            query = query.filter(AuditLog.created_at < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        pass

    total = query.order_by(None).count()
    raw_rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    rows = [SimpleNamespace(
        id=row.id, user_id=row.user_id, action=row.action, description=row.description,
        created_at=row.created_at, ip_address=row.ip_address, request_id=None,
        endpoint=None, entity_type=None, entity_id=None,
    ) for row in raw_rows]
    pages = max((total + per_page - 1) // per_page, 1)
    pagination = SimpleNamespace(
        items=rows, total=total, page=page, pages=pages,
        has_prev=page > 1, prev_num=page - 1,
        has_next=page < pages, next_num=page + 1,
    )

    user_rows = db.session.query(User.id, User.name).filter(User.company_id == company_id).order_by(User.name).all()
    users = [SimpleNamespace(id=row.id, name=row.name, avatar_path=None) for row in user_rows]
    actors = {actor.id: actor for actor in users}
    events = [
        {'row': row, 'actor': actors.get(row.user_id), 'meta': _audit_presentation(row)}
        for row in rows
    ]

    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now - timedelta(days=30)
    today_count = db.session.query(func.count(AuditLog.id)).filter(
        AuditLog.company_id == company_id, AuditLog.created_at >= today_start,
    ).scalar() or 0
    active_actors = db.session.query(func.count(func.distinct(AuditLog.user_id))).filter(
        AuditLog.company_id == company_id, AuditLog.user_id.isnot(None), AuditLog.created_at >= month_start,
    ).scalar() or 0
    security_count = db.session.query(func.count(AuditLog.id)).filter(
        AuditLog.company_id == company_id, AuditLog.created_at >= month_start,
        or_(AuditLog.action.ilike('%SECURITY%'), AuditLog.action.ilike('%TWO_FACTOR%'), AuditLog.action.ilike('%LOGIN%'), AuditLog.action.ilike('%SESSION%')),
    ).scalar() or 0
    action_values = [row[0] for row in db.session.query(AuditLog.action).filter(
        AuditLog.company_id == company_id, AuditLog.action.isnot(None),
    ).distinct().order_by(AuditLog.action.asc()).limit(120).all()]
    action_options = [{'value': value, 'label': _audit_action_label(value)} for value in action_values]
    return {
        'pagination': pagination, 'rows': rows, 'events': events, 'users': users,
        'action_options': action_options, 'today_count': int(today_count),
        'active_actors': int(active_actors), 'security_count': int(security_count),
        'audit_compat_mode': True,
    }


@governance_bp.get('/audit')
def audit_explorer():
    company_id, user_id = _identity()
    required_columns = {'request_id', 'endpoint', 'entity_type', 'entity_id'}
    audit_columns = _audit_schema_columns()

    if audit_columns and not required_columns.issubset(audit_columns):
        payload = _legacy_audit_payload(company_id)
        payload['user'] = db.session.get(User, user_id)
        return render_template('governance/audit.html', **payload)

    try:
        pagination = _audit_query(company_id).paginate(
            page=max(request.args.get('page', 1, type=int) or 1, 1), per_page=_page_size(), error_out=False,
        )
        users = User.query.filter_by(company_id=company_id).order_by(User.name).all()
        actors = {actor.id: actor for actor in users}
        events = [
            {'row': row, 'actor': actors.get(row.user_id), 'meta': _audit_presentation(row)}
            for row in pagination.items
        ]
        now = utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now - timedelta(days=30)
        base = AuditLog.query.filter(AuditLog.company_id == company_id)
        today_count = base.filter(AuditLog.created_at >= today_start).count()
        active_actors = db.session.query(func.count(func.distinct(AuditLog.user_id))).filter(
            AuditLog.company_id == company_id, AuditLog.user_id.isnot(None), AuditLog.created_at >= month_start
        ).scalar() or 0
        security_count = base.filter(
            AuditLog.created_at >= month_start,
            or_(
                AuditLog.action.ilike('%SECURITY%'), AuditLog.action.ilike('%TWO_FACTOR%'),
                AuditLog.endpoint.ilike('%login%'), AuditLog.endpoint.ilike('%session%'),
                AuditLog.endpoint.ilike('%user%'),
            ),
        ).count()
        action_values = [row[0] for row in db.session.query(AuditLog.action).filter(
            AuditLog.company_id == company_id, AuditLog.action.isnot(None)
        ).distinct().order_by(AuditLog.action.asc()).limit(120).all()]
        action_options = [{'value': value, 'label': _audit_action_label(value)} for value in action_values]
        return render_template(
            'governance/audit.html', user=db.session.get(User, user_id), pagination=pagination,
            rows=pagination.items, events=events, users=users, action_options=action_options,
            today_count=today_count, active_actors=int(active_actors), security_count=security_count,
            audit_compat_mode=False,
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Audit explorer failed with current schema; using compatibility mode')
        payload = _legacy_audit_payload(company_id)
        payload['user'] = db.session.get(User, user_id)
        return render_template('governance/audit.html', **payload)


@governance_bp.get('/audit.csv')
def audit_export():
    company_id, _ = _identity()
    rows = _audit_query(company_id).limit(10_000).all()
    actor_ids = {row.user_id for row in rows if row.user_id}
    actors = {user.id: user.name for user in User.query.filter(User.company_id == company_id, User.id.in_(actor_ids)).all()} if actor_ids else {}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['fecha', 'usuario', 'accion', 'endpoint', 'entidad', 'descripcion', 'ip', 'request_id'])
    for row in rows:
        writer.writerow(safe_csv_row([
            row.created_at.isoformat() if row.created_at else '', actors.get(row.user_id, 'Sistema'),
            row.action, row.endpoint, f'{row.entity_type or ""}:{row.entity_id or ""}',
            row.description, row.ip_address, row.request_id,
        ]))
    return Response(
        '\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=orbiserp_auditoria.csv'},
    )


def _database_status():
    started = time.perf_counter()
    try:
        db.session.execute(text('SELECT 1'))
        revision = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        return {
            'ok': True, 'latency_ms': round((time.perf_counter() - started) * 1000, 1),
            'revision': revision, 'expected': current_app.config['EXPECTED_SCHEMA_REVISION'],
            'pool': db.engine.pool.status(),
        }
    except Exception:
        db.session.rollback()
        return {'ok': False, 'latency_ms': None, 'revision': None, 'expected': current_app.config['EXPECTED_SCHEMA_REVISION'], 'pool': 'No disponible'}


@governance_bp.get('/system')
def system_status():
    _, user_id = _identity()
    storage = Path(current_app.config['STORAGE_ROOT'])
    storage.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(storage)
    backup_file = Path(current_app.config['BACKUP_STATUS_FILE'])
    backup_at = datetime.fromtimestamp(backup_file.stat().st_mtime) if backup_file.is_file() else None
    backup_max_age = int(current_app.config.get('BACKUP_MAX_AGE_HOURS', 30))
    backup_fresh = bool(backup_at and backup_at >= datetime.now() - timedelta(hours=backup_max_age))
    database = _database_status()
    services = [
        {'name': 'PostgreSQL', 'ok': database['ok'], 'detail': f"{database['latency_ms']} ms" if database['ok'] else 'Sin conexión'},
        {'name': 'Migraciones', 'ok': database['revision'] == database['expected'], 'detail': database['revision'] or 'No disponible'},
        {'name': 'Almacenamiento', 'ok': os.access(storage, os.R_OK | os.W_OK), 'detail': f'{disk.free / 1024**3:.1f} GB libres'},
        {'name': 'Correo', 'ok': bool(current_app.config['MAIL_USERNAME'] and current_app.config['MAIL_PASSWORD']), 'detail': 'Configurado' if current_app.config['MAIL_USERNAME'] else 'Pendiente'},
        {'name': 'Backup reciente', 'ok': backup_fresh, 'detail': (backup_at.strftime('%d/%m/%Y %H:%M') + f' · máximo {backup_max_age} h') if backup_at else 'Sin evidencia'},
        {'name': 'Verificación de correo', 'ok': bool(current_app.config.get('REQUIRE_EMAIL_VERIFICATION')), 'detail': 'Obligatoria' if current_app.config.get('REQUIRE_EMAIL_VERIFICATION') else 'Desactivada'},
    ]
    return render_template(
        'governance/system.html', user=db.session.get(User, user_id), services=services,
        database=database, disk=disk, storage=storage, backup_at=backup_at,
        release=current_app.config['RELEASE_VERSION'], now=datetime.now(),
    )


@governance_bp.get('/processes')
def processes():
    company_id, user_id = _identity()
    query = OperationJob.query.filter_by(company_id=company_id)
    status = (request.args.get('status') or '').upper()
    if status in {'PENDING', 'RUNNING', 'COMPLETED', 'FAILED'}:
        query = query.filter_by(status=status)
    pagination = query.order_by(OperationJob.created_at.desc()).paginate(
        page=max(request.args.get('page', 1, type=int) or 1, 1), per_page=_page_size(), error_out=False,
    )
    counts = dict(db.session.query(OperationJob.status, func.count(OperationJob.id)).filter(
        OperationJob.company_id == company_id
    ).group_by(OperationJob.status).all())
    return render_template(
        'governance/processes.html', user=db.session.get(User, user_id),
        rows=pagination.items, pagination=pagination, counts=counts,
    )


@governance_bp.get('/sessions')
def sessions_view():
    company_id, user_id = _identity()
    current_user = db.session.get(User, user_id)
    query = UserSession.query.filter(UserSession.revoked_at.is_(None))
    if current_user.role in {'admin', 'superadmin'}:
        query = query.filter(UserSession.company_id == company_id)
    else:
        query = query.filter(UserSession.user_id == user_id)
    pagination = query.order_by(UserSession.last_seen_at.desc()).paginate(
        page=max(request.args.get('page', 1, type=int) or 1, 1), per_page=_page_size(), error_out=False,
    )
    current_hash = hashlib.sha256((session.get('server_session_token') or '').encode()).hexdigest()
    return render_template(
        'governance/sessions.html', user=current_user, rows=pagination.items,
        pagination=pagination, current_hash=current_hash,
    )


@governance_bp.post('/sessions/<int:session_id>/revoke')
def revoke_session(session_id):
    company_id, user_id = _identity()
    current_user = db.session.get(User, user_id)
    row = UserSession.query.filter_by(id=session_id).with_for_update().first_or_404()
    if row.user_id != user_id and not (current_user.role in {'admin', 'superadmin'} and row.company_id == company_id):
        abort(403)
    row.revoked_at = utcnow()
    row.revoke_reason = 'Revocada manualmente'
    db.session.commit()
    token_hash = hashlib.sha256((session.get('server_session_token') or '').encode()).hexdigest()
    if row.session_hash == token_hash:
        session.clear()
        flash('La sesión actual fue cerrada.', 'info')
        return redirect(url_for('login_bp.login'))
    flash('Sesión revocada.', 'success')
    return redirect(url_for('governance_bp.sessions_view'))


@governance_bp.post('/sessions/revoke-all')
def revoke_all_sessions():
    _, user_id = _identity()
    current_hash = hashlib.sha256((session.get('server_session_token') or '').encode()).hexdigest()
    now = utcnow()
    UserSession.query.filter(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
        UserSession.session_hash != current_hash,
    ).update({'revoked_at': now, 'revoke_reason': 'Cierre masivo'}, synchronize_session=False)
    db.session.commit()
    flash('Las demás sesiones fueron cerradas.', 'success')
    return redirect(url_for('governance_bp.sessions_view'))
