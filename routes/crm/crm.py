from flask import Blueprint, render_template, session, request, jsonify, redirect, url_for
from sqlalchemy.orm import joinedload
from sqlalchemy import select
from datetime import datetime, timezone
from models.client.client import Client, Interaction
from models.user.user import User
from models.crm.crm import Task, Opportunity
from db import db
from decimal import Decimal
from models.divisas.divisas import ExchangeRate

crm_bp = Blueprint('crm_bp', __name__)

# ==========================================================
# VISTA PRINCIPAL: CARGA DE INTERFAZ
# ==========================================================
@crm_bp.route('/crm')
def crm_index():
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = db.session.get(User, user_id)
    
    stmt = select(Client).filter_by(company_id=company_id).order_by(Client.name.asc())
    clientes = db.session.execute(stmt).scalars().all()
    tasks_due = db.session.execute(
        select(Task).join(Client).where(
            Client.company_id == company_id,
            Task.is_completed.is_(False),
        ).order_by(Task.due_date.asc()).limit(8)
    ).scalars().all()
    stats = {
        'clients': len(clientes),
        'leads': sum(1 for c in clientes if (c.status or 'Lead') == 'Lead'),
        'negotiation': sum(1 for c in clientes if c.status == 'Negociacion'),
        'won': sum(1 for c in clientes if c.status == 'Ganado'),
        'pending_tasks': len(tasks_due),
    }
    return render_template('crm/index.html', clientes=clientes, user=user, stats=stats, tasks_due=tasks_due)

@crm_bp.route('/crm/api/client/<int:client_id>')
def get_client_details(client_id):
    company_id = session.get('company_id')
    if not session.get('user_id') or not company_id:
        return jsonify({"status": "error", "message": "Autenticación requerida"}), 401
    
    # --- LÓGICA DE DIVISAS ---
    selected_currency = session.get('selected_currency', 'DOP')
    rate_val = ExchangeRate.get_rate(selected_currency, company_id)
    conversion_rate = Decimal(str(rate_val or 1))
    if conversion_rate <= 0:
        conversion_rate = Decimal('1')
    
    rate_row = ExchangeRate.query.filter_by(currency_code=selected_currency, company_id=company_id).first()
    currency_symbol = rate_row.symbol if rate_row else 'RD$'
    # -------------------------

    stmt = select(Client).filter_by(id=client_id, company_id=company_id).options(
        joinedload(Client.interactions).joinedload(Interaction.user),
        joinedload(Client.sales)
    )
    cliente = db.session.execute(stmt).unique().scalar_one_or_none()

    if not cliente:
        return jsonify({"status": "error", "message": "No encontrado"}), 404

    stmt_tasks = select(Task).filter_by(client_id=client_id, is_completed=False).order_by(Task.due_date.asc())
    tareas = db.session.execute(stmt_tasks).scalars().all()

    # Cálculo de montos convertidos
    total_debt = sum((Decimal(str(s.balance)) for s in cliente.sales if s.balance and s.balance > 0), Decimal('0'))
    total_sales = sum((Decimal(str(s.total or 0)) for s in cliente.sales), Decimal('0'))
    
    # Aplicar conversión
    total_debt_converted = total_debt / conversion_rate
    total_sales_converted = total_sales / conversion_rate

    return jsonify({
        "id": cliente.id,
        "name": cliente.name,
        "email": cliente.email or "Sin correo",
        "phone": cliente.phone or "Sin teléfono",
        "status": cliente.status or "Lead",
        
        # Enviamos el símbolo y los montos ya calculados
        "currency_symbol": currency_symbol,
        "ltv": f"{currency_symbol} {total_sales_converted:,.2f}",
        
        "has_debt": total_debt > 0,
        "total_debt_format": f"{currency_symbol} {total_debt_converted:,.2f}",
        "total_debt_raw": float(total_debt_converted),

        "interactions": [{
            "id": i.id,
            "content": i.content,
            "type": i.type,
            "date": i.created_at.strftime('%d %b, %H:%M') if i.created_at else 'Sin fecha',
            "user": i.user.name if i.user else "Sistema"
        } for i in sorted(cliente.interactions, key=lambda x: x.created_at.timestamp() if x.created_at else 0, reverse=True)],
        
        "tasks": [{
            "id": t.id,
            "title": t.title,
            "due": t.due_date.strftime('%d %b %Y') if t.due_date else 'Sin fecha',
            "due_iso": t.due_date.strftime('%Y-%m-%d') if t.due_date else '',
            "priority": t.priority or 'Media'
        } for t in tareas]
    })
    
# ==========================================================
# API: REGISTRAR NOTAS / INTERACCIONES
# ==========================================================
@crm_bp.route('/crm/api/add_interaction', methods=['POST'])
def add_interaction():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    data = request.get_json(silent=True) or {}
    if not user_id or not company_id:
        return jsonify({"status": "error", "message": "Autenticación requerida"}), 401
    content = (data.get('content') or '').strip()
    if not content or len(content) > 2000:
        return jsonify({"status": "error", "message": "La nota debe tener entre 1 y 2000 caracteres"}), 400
    
    try:
        client_id = int(data.get('client_id'))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "ID de cliente inválido"}), 400

    stmt = select(Client).filter_by(id=client_id, company_id=company_id)
    cliente = db.session.execute(stmt).scalar_one_or_none()
    
    if not cliente:
        return jsonify({"status": "error", "message": "Acceso denegado"}), 403

    nueva_nota = Interaction(
        content=content,
        client_id=client_id,
        user_id=user_id,
        type=data.get('type', 'Nota'),
        created_at=datetime.now(timezone.utc)
    )

    db.session.add(nueva_nota)
    db.session.commit()
    return jsonify({"status": "success"})


# ==========================================================
# API: ACTUALIZAR FASE DEL EMBUDO (PIPELINE)
# ==========================================================
@crm_bp.route('/crm/api/update_status', methods=['POST'])
def update_status():
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    if not user_id or not company_id:
        return jsonify({"status": "error", "message": "Autenticación requerida"}), 401
    try:
        client_id = int(data.get('client_id'))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "ID de cliente inválido"}), 400
    
    stmt = select(Client).filter_by(id=client_id, company_id=company_id)
    cliente = db.session.execute(stmt).scalar_one_or_none()
    
    if not cliente: 
        return jsonify({"status": "error"}), 404

    old_status = cliente.status
    new_status = data.get('status')
    if new_status not in {'Lead', 'Negociacion', 'Ganado', 'Perdido'}:
        return jsonify({"status": "error", "message": "Fase no válida"}), 400
    cliente.status = new_status

    log = Interaction(
        content=f"Fase actualizada: {old_status or 'Nuevo'} → {new_status}",
        client_id=cliente.id,
        user_id=user_id,
        type='Sistema',
        created_at=datetime.now(timezone.utc)
    )
    
    db.session.add(log)
    db.session.commit()
    return jsonify({"status": "success"})


# ==========================================================
# API: AGENDAR TAREA DE SEGUIMIENTO
# ==========================================================
@crm_bp.route('/crm/api/add_task', methods=['POST'])
def add_task():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    data = request.get_json(silent=True) or {}
    if not user_id or not company_id:
        return jsonify({"status": "error", "message": "Autenticación requerida"}), 401
    try:
        client_id = int(data.get('client_id'))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "ID de cliente inválido"}), 400
    
    stmt = select(Client).filter_by(id=client_id, company_id=company_id)
    cliente = db.session.execute(stmt).scalar_one_or_none()
    
    if not cliente:
        return jsonify({"status": "error", "message": "Cliente no válido"}), 403

    try:
        title = (data.get('title') or '').strip()
        if not title or len(title) > 200:
            return jsonify({"status": "error", "message": "Escribe un título válido"}), 400
        priority = data.get('priority', 'Media')
        if priority not in {'Baja', 'Media', 'Alta'}:
            priority = 'Media'
        nueva_tarea = Task(
            title=title,
            due_date=datetime.strptime(data.get('due_date'), '%Y-%m-%d'),
            client_id=cliente.id,
            user_id=user_id,
            priority=priority,
            is_completed=False,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(nueva_tarea)
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================================
# API: MARCAR TAREA COMO COMPLETADA
# ==========================================================
@crm_bp.route('/crm/api/complete_task/<int:task_id>', methods=['POST'])
def complete_task(task_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not user_id or not company_id:
        return jsonify({"status": "error", "message": "Autenticación requerida"}), 401
    task = db.session.execute(
        select(Task).join(Client).where(Task.id == task_id, Client.company_id == company_id)
    ).scalar_one_or_none()
    if not task:
        return jsonify({"status": "error"}), 404
    
    task.is_completed = True
    db.session.commit()
    return jsonify({"status": "success"})
