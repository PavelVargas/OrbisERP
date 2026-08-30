from services.time_utils import utcnow
from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from db import db
from models.client.client import Client, Interaction
from models.crm.crm import Task
from models.sales.sales import Sale
from models.divisas.divisas import ExchangeRate
from models.user.user import User
from services.numeric import finite_decimal
from services.validation import BusinessRuleError, tenant_id


crm_bp = Blueprint('crm_bp', __name__)
CRM_STAGES = ('Lead', 'Negociacion', 'Ganado', 'Perdido')
INTERACTION_TYPES = {'Nota', 'Llamada', 'Correo', 'Reunión', 'Sistema'}
TASK_PRIORITIES = {'Baja', 'Media', 'Alta'}


def _identity():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return None, None
    return int(user_id), int(company_id)


def _client(company_id, client_id):
    return db.session.execute(
        select(Client).where(
            Client.id == client_id,
            Client.company_id == company_id,
            Client.archived_at.is_(None),
        )
    ).scalar_one_or_none()


def _display_currency(company_id):
    """Return a local display rate without making an external network call.

    CRM reads must stay fast and deterministic. Exchange-rate refreshes belong to
    the currency management flow, not to opening a customer dossier.
    """
    selected_currency = (session.get('selected_currency') or 'DOP').upper()
    if selected_currency == 'DOP':
        return Decimal('1'), 'RD$'

    rate_row = ExchangeRate.query.filter_by(
        currency_code=selected_currency,
        company_id=company_id,
    ).first()
    if not rate_row:
        return Decimal('1'), selected_currency

    try:
        conversion_rate = finite_decimal(rate_row.rate, field_name='Tasa de conversión')
        if conversion_rate <= 0:
            raise BusinessRuleError('La tasa de conversión debe ser positiva.')
    except (BusinessRuleError, TypeError, ValueError):
        conversion_rate = Decimal('1')
    return conversion_rate, (rate_row.symbol or selected_currency)


def _client_payload(company_id, client_id):
    """Build the CRM dossier with bounded, independent queries.

    Avoid joined-loading both sales and interactions at once: that creates a
    cartesian product that becomes very expensive for active customers and was
    able to leave the browser waiting on the CRM loader.
    """
    cliente = _client(company_id, client_id)
    if not cliente:
        return None

    conversion_rate, currency_symbol = _display_currency(company_id)

    sales_row = db.session.execute(
        select(
            func.coalesce(func.sum(Sale.total), 0),
            func.count(Sale.id),
            func.coalesce(func.avg(Sale.total), 0),
            func.max(Sale.created_at),
            func.coalesce(func.sum(Sale.balance), 0),
        ).where(
            Sale.client_id == cliente.id,
            Sale.company_id == company_id,
            Sale.status == 'COMPLETED',
        )
    ).one()
    total_sales = Decimal(str(sales_row[0] or 0))
    sales_count = int(sales_row[1] or 0)
    average_ticket = Decimal(str(sales_row[2] or 0))
    last_sale = sales_row[3]
    total_debt = Decimal(str(sales_row[4] or 0))

    tareas = db.session.execute(
        select(Task).where(
            Task.client_id == cliente.id,
            Task.is_completed.is_(False),
        ).order_by(Task.due_date.asc()).limit(100)
    ).scalars().all()

    interactions = db.session.execute(
        select(Interaction).where(Interaction.client_id == cliente.id)
        .options(joinedload(Interaction.user))
        .order_by(Interaction.created_at.desc(), Interaction.id.desc())
        .limit(120)
    ).scalars().all()

    status = cliente.status if cliente.status in CRM_STAGES else 'Lead'
    today = utcnow().date()
    return {
        'id': cliente.id,
        'name': cliente.name,
        'email': cliente.email or 'Sin correo',
        'phone': cliente.phone or 'Sin teléfono',
        'status': status,
        'currency_symbol': currency_symbol,
        'ltv': f'{currency_symbol} {total_sales / conversion_rate:,.2f}',
        'average_ticket': f'{currency_symbol} {average_ticket / conversion_rate:,.2f}',
        'sales_count': sales_count,
        'last_sale': last_sale.strftime('%d/%m/%Y') if last_sale else 'Sin ventas',
        'has_debt': total_debt > 0,
        'total_debt_format': f'{currency_symbol} {total_debt / conversion_rate:,.2f}',
        'pending_tasks': len(tareas),
        'detail_url': url_for('client_bp.client_detail', client_id=cliente.id),
        'interactions': [{
            'id': item.id,
            'content': item.content,
            'type': item.type or 'Nota',
            'date': item.created_at.strftime('%d %b %Y · %H:%M') if item.created_at else 'Sin fecha',
            'user': item.user.name if item.user else 'Sistema',
            'user_avatar': url_for('static', filename=item.user.avatar_path) if item.user and item.user.avatar_path else None,
        } for item in interactions],
        'tasks': [{
            'id': task.id,
            'title': task.title,
            'due': task.due_date.strftime('%d/%m/%Y') if task.due_date else 'Sin fecha',
            'due_iso': task.due_date.strftime('%Y-%m-%d') if task.due_date else '',
            'priority': task.priority if task.priority in TASK_PRIORITIES else 'Media',
            'overdue': bool(task.due_date and task.due_date.date() < today),
        } for task in tareas],
    }


@crm_bp.route('/crm')
def crm_index():
    user_id, company_id = _identity()
    if not user_id:
        return redirect(url_for('login_bp.login'))
    user = db.session.get(User, user_id)
    clientes = db.session.execute(
        select(Client).where(
            Client.company_id == company_id,
            Client.archived_at.is_(None),
        ).order_by(Client.name.asc())
    ).scalars().all()
    tasks_due = db.session.execute(
        select(Task).join(Client).where(
            Client.company_id == company_id,
            Client.archived_at.is_(None),
            Task.is_completed.is_(False),
        ).order_by(Task.due_date.asc()).limit(10)
    ).scalars().all()
    stats = {
        'clients': len(clientes),
        'leads': sum(1 for c in clientes if (c.status or 'Lead') == 'Lead'),
        'negotiation': sum(1 for c in clientes if c.status == 'Negociacion'),
        'won': sum(1 for c in clientes if c.status == 'Ganado'),
        'pending_tasks': db.session.execute(
            select(func.count(Task.id)).join(Client).where(
                Client.company_id == company_id,
                Client.archived_at.is_(None),
                Task.is_completed.is_(False),
            )
        ).scalar_one(),
    }
    requested_client_id = request.args.get('client', type=int)
    valid_client_ids = {client.id for client in clientes}
    initial_client_id = requested_client_id if requested_client_id in valid_client_ids else (clientes[0].id if clientes else None)
    initial_client = _client_payload(company_id, initial_client_id) if initial_client_id else None
    return render_template(
        'crm/index.html',
        clientes=clientes,
        user=user,
        stats=stats,
        tasks_due=tasks_due,
        initial_client=initial_client,
        initial_client_id=initial_client_id,
    )


@crm_bp.route('/crm/api/client/<int:client_id>')
def get_client_details(client_id):
    user_id, company_id = _identity()
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Autenticación requerida'}), 401

    payload = _client_payload(company_id, client_id)
    if not payload:
        return jsonify({'status': 'error', 'message': 'Cliente no encontrado'}), 404
    return jsonify(payload)


@crm_bp.route('/crm/api/add_interaction', methods=['POST'])
def add_interaction():
    user_id, company_id = _identity()
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Autenticación requerida'}), 401
    data = request.get_json(silent=True) or {}
    content = (data.get('content') or '').strip()
    if not content or len(content) > 2000:
        return jsonify({'status': 'error', 'message': 'La actividad debe tener entre 1 y 2000 caracteres'}), 400
    try:
        client_id = tenant_id(data.get('client_id'), 'Cliente')
    except BusinessRuleError:
        return jsonify({'status': 'error', 'message': 'ID de cliente inválido'}), 400
    cliente = _client(company_id, client_id)
    if not cliente:
        return jsonify({'status': 'error', 'message': 'Cliente no válido'}), 404
    interaction_type = data.get('type', 'Nota')
    if interaction_type not in INTERACTION_TYPES:
        interaction_type = 'Nota'
    db.session.add(Interaction(
        content=content,
        client_id=cliente.id,
        user_id=user_id,
        type=interaction_type,
        created_at=datetime.now(timezone.utc),
    ))
    db.session.commit()
    return jsonify({'status': 'success'})


@crm_bp.route('/crm/api/update_status', methods=['POST'])
def update_status():
    user_id, company_id = _identity()
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Autenticación requerida'}), 401
    data = request.get_json(silent=True) or {}
    try:
        client_id = tenant_id(data.get('client_id'), 'Cliente')
    except BusinessRuleError:
        return jsonify({'status': 'error', 'message': 'ID de cliente inválido'}), 400
    cliente = _client(company_id, client_id)
    if not cliente:
        return jsonify({'status': 'error', 'message': 'Cliente no encontrado'}), 404
    new_status = data.get('status')
    if new_status not in CRM_STAGES:
        return jsonify({'status': 'error', 'message': 'Fase no válida'}), 400
    old_status = cliente.status if cliente.status in CRM_STAGES else 'Lead'
    if new_status != old_status:
        cliente.status = new_status
        db.session.add(Interaction(
            content=f'Fase comercial actualizada: {old_status} → {new_status}',
            client_id=cliente.id,
            user_id=user_id,
            type='Sistema',
            created_at=datetime.now(timezone.utc),
        ))
        db.session.commit()
    return jsonify({'status': 'success', 'status_value': new_status})


@crm_bp.route('/crm/api/add_task', methods=['POST'])
def add_task():
    user_id, company_id = _identity()
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Autenticación requerida'}), 401
    data = request.get_json(silent=True) or {}
    try:
        client_id = tenant_id(data.get('client_id'), 'Cliente')
    except BusinessRuleError:
        return jsonify({'status': 'error', 'message': 'ID de cliente inválido'}), 400
    cliente = _client(company_id, client_id)
    if not cliente:
        return jsonify({'status': 'error', 'message': 'Cliente no válido'}), 404
    title = (data.get('title') or '').strip()
    if not title or len(title) > 200:
        return jsonify({'status': 'error', 'message': 'Escribe un título entre 1 y 200 caracteres'}), 400
    try:
        due_date = datetime.strptime(data.get('due_date') or '', '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Selecciona una fecha válida'}), 400
    priority = data.get('priority', 'Media')
    if priority not in TASK_PRIORITIES:
        priority = 'Media'
    task = Task(
        title=title,
        due_date=due_date,
        client_id=cliente.id,
        user_id=user_id,
        priority=priority,
        is_completed=False,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(task)
    db.session.add(Interaction(
        content=f'Tarea programada: {title} · {due_date:%d/%m/%Y} · prioridad {priority}',
        client_id=cliente.id,
        user_id=user_id,
        type='Sistema',
        created_at=datetime.now(timezone.utc),
    ))
    db.session.commit()
    return jsonify({'status': 'success', 'task_id': task.id})


@crm_bp.route('/crm/api/complete_task/<int:task_id>', methods=['POST'])
def complete_task(task_id):
    user_id, company_id = _identity()
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Autenticación requerida'}), 401
    task = db.session.execute(
        select(Task).join(Client).where(
            Task.id == task_id,
            Client.company_id == company_id,
            Client.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if not task:
        return jsonify({'status': 'error', 'message': 'Tarea no encontrada'}), 404
    if not task.is_completed:
        task.is_completed = True
        db.session.add(Interaction(
            content=f'Tarea completada: {task.title}',
            client_id=task.client_id,
            user_id=user_id,
            type='Sistema',
            created_at=datetime.now(timezone.utc),
        ))
        db.session.commit()
    return jsonify({'status': 'success'})
