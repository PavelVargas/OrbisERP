from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models.client.client import Client
from models.sales.sales import Sale
from models.user.user import User
from db import db

client_bp = Blueprint('client_bp', __name__, url_prefix='/clients')

# =====================
# LISTAR CLIENTES
# =====================
@client_bp.route('/')
def list_clients():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    # 🔒 FILTRO CRÍTICO: Solo clientes de esta empresa
    clients = Client.query.filter_by(company_id=company_id).order_by(Client.name.asc()).all()
    
    return render_template('clients/list.html', clients=clients, user=user)


# =====================
# CREAR CLIENTE
# =====================
@client_bp.route('/create', methods=['GET', 'POST'])
def create_client():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)

    if request.method == 'POST':
        name = request.form['name']
        email = request.form.get('email')
        phone = request.form.get('phone')

        if not name:
            flash('El nombre es obligatorio', 'danger')
            return redirect(url_for('client_bp.create_client'))

        # 🔒 ASIGNACIÓN SEGURA: Se vincula al company_id de la sesión
        client = Client(
            name=name,
            email=email,
            phone=phone,
            company_id=company_id
        )
        db.session.add(client)
        db.session.commit()
        flash(f'Cliente "{name}" creado correctamente', 'success')
        return redirect(url_for('client_bp.list_clients'))

    return render_template('clients/create.html', user=user)


# =====================
# EDITAR CLIENTE
# =====================
@client_bp.route('/edit/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    # 🔒 PROTECCIÓN: filter_by(company_id) evita que editen clientes ajenos
    client = Client.query.filter_by(id=client_id, company_id=company_id).first()
    
    if not client:
        flash('No tienes permiso para editar este cliente o no existe.', 'danger')
        return redirect(url_for('client_bp.list_clients'))

    if request.method == 'POST':
        client.name = request.form['name']
        client.email = request.form.get('email')
        client.phone = request.form.get('phone')
        db.session.commit()
        flash(f'Cliente "{client.name}" actualizado', 'success')
        return redirect(url_for('client_bp.list_clients'))

    return render_template('clients/edit.html', client=client, user=user)


# =====================
# ELIMINAR CLIENTE
# =====================
@client_bp.route('/delete/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    company_id = session.get('company_id')
    if not company_id:
        return redirect(url_for('login_bp.login'))

    # 🔒 PROTECCIÓN: Asegura que el cliente pertenece a la empresa
    client = Client.query.filter_by(id=client_id, company_id=company_id).first()
    
    if not client:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('client_bp.list_clients'))

    db.session.delete(client)
    db.session.commit()
    flash(f'Cliente "{client.name}" eliminado', 'info')
    return redirect(url_for('client_bp.list_clients'))


@client_bp.route('/<int:client_id>')
def client_detail(client_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    selected_currency = session.get('selected_currency', 'DOP')
    conversion_rate = float(session.get('conversion_rate', 1.0))
    currency_symbol = session.get('currency_symbol', 'RD$')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    client = Client.query.filter_by(id=client_id, company_id=company_id).first()
    
    if not client:
        flash('Cliente no encontrado.', 'danger')
        return redirect(url_for('client_bp.list_clients'))

    # 2. Obtener las ventas (los montos en BD suelen estar en la moneda base, ej: DOP)
    raw_sales = Sale.query.filter_by(
        client_id=client.id,
        company_id=company_id,
        status='COMPLETED'
    ).order_by(Sale.created_at.desc()).all()

    # 3. REALIZAR LA CONVERSIÓN MATEMÁTICA
    processed_sales = []
    total_spent_converted = 0
    
    for sale in raw_sales:
        # Dividimos el monto de la base de datos entre la tasa de cambio
        monto_convertido = float(sale.total or 0) / conversion_rate
        total_spent_converted += monto_convertido
        
        # Creamos un objeto temporal para el frontend
        processed_sales.append({
            'id': sale.id,
            'created_at': sale.created_at,
            'total': monto_convertido
        })

    total_sales = len(processed_sales)
    last_sale = processed_sales[0]['created_at'] if processed_sales else None

    return render_template(
        'clients/detail.html',
        client=client,
        sales=processed_sales, # Enviamos la lista ya convertida
        total_spent=total_spent_converted,
        total_sales=total_sales,
        last_sale=last_sale,
        user=user,
        currency_symbol=currency_symbol,
        selected_currency=selected_currency
    )