from services.time_utils import utcnow
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import date, datetime
from models.client.client import Client
from models.sales.sales import Sale
from models.backoffice import CustomerPayment, SaleReturn
from models.productivity import CompanyDocument
from models.divisas.divisas import ExchangeRate
from models.user.user import User
from models.retail import PriceList, GiftCard, Layaway, LoyaltyTransaction
from db import db
from services.money import as_decimal, exchange_rate
from services.numeric import bounded_decimal
from services.validation import BusinessRuleError, non_negative_integer

client_bp = Blueprint('client_bp', __name__, url_prefix='/clients')


def _credit_values(form):
    credit_limit = bounded_decimal(
        form.get('credit_limit') or '0',
        field_name='Límite de crédito',
        places=2,
        minimum='0',
        maximum='9999999999.99',
    )
    payment_terms_days = non_negative_integer(
        form.get('payment_terms_days') or '0',
        'Días de crédito',
        maximum=3650,
    )
    return credit_limit, payment_terms_days


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
    clients = Client.query.filter_by(company_id=company_id).filter(Client.archived_at.is_(None)).order_by(Client.name.asc()).all()
    
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
    price_lists = PriceList.query.filter_by(company_id=company_id, active=True).order_by(PriceList.is_default.desc(), PriceList.name.asc()).all()

    if request.method == 'POST':
        name = request.form['name'].strip()
        email = (request.form.get('email') or '').strip() or None
        phone = (request.form.get('phone') or '').strip() or None

        if not name:
            flash('El nombre es obligatorio', 'danger')
            return redirect(url_for('client_bp.create_client'))

        # 🔒 ASIGNACIÓN SEGURA: Se vincula al company_id de la sesión
        price_list_id = request.form.get('price_list_id', type=int)
        if price_list_id and not PriceList.query.filter_by(id=price_list_id, company_id=company_id, active=True).first():
            price_list_id = None
        try:
            credit_limit, payment_terms_days = _credit_values(request.form)
        except BusinessRuleError:
            flash('Los datos de crédito no son válidos.', 'danger')
            return redirect(url_for('client_bp.create_client'))
        client = Client(
            name=name, email=email, phone=phone, company_id=company_id,
            price_list_id=price_list_id,
            credit_enabled=request.form.get('credit_enabled') == '1',
            credit_limit=credit_limit, payment_terms_days=payment_terms_days,
            credit_hold=request.form.get('credit_hold') == '1'
        )
        db.session.add(client)
        db.session.commit()
        flash(f'Cliente "{name}" creado correctamente', 'success')
        return redirect(url_for('client_bp.list_clients'))

    return render_template('clients/create.html', user=user, price_lists=price_lists)


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
    price_lists = PriceList.query.filter_by(company_id=company_id, active=True).order_by(PriceList.is_default.desc(), PriceList.name.asc()).all()
    # 🔒 PROTECCIÓN: filter_by(company_id) evita que editen clientes ajenos
    client = Client.query.filter_by(id=client_id, company_id=company_id).filter(Client.archived_at.is_(None)).first()
    
    if not client:
        flash('No tienes permiso para editar este cliente o no existe.', 'danger')
        return redirect(url_for('client_bp.list_clients'))

    if request.method == 'POST':
        client.name = request.form['name'].strip()
        client.email = (request.form.get('email') or '').strip() or None
        client.phone = (request.form.get('phone') or '').strip() or None
        price_list_id = request.form.get('price_list_id', type=int)
        if price_list_id and not PriceList.query.filter_by(id=price_list_id, company_id=company_id, active=True).first():
            price_list_id = None
        try:
            credit_limit, client.payment_terms_days = _credit_values(request.form)
        except BusinessRuleError:
            flash('Los datos de crédito no son válidos.', 'danger')
            return redirect(url_for('client_bp.edit_client', client_id=client.id))
        client.price_list_id = price_list_id
        client.credit_enabled = request.form.get('credit_enabled') == '1'
        client.credit_limit = credit_limit
        client.credit_hold = request.form.get('credit_hold') == '1'
        db.session.commit()
        flash(f'Cliente "{client.name}" actualizado', 'success')
        return redirect(url_for('client_bp.list_clients'))

    return render_template('clients/edit.html', client=client, user=user, price_lists=price_lists)


# =====================
# ELIMINAR CLIENTE
# =====================
@client_bp.route('/delete/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    company_id = session.get('company_id')
    if not company_id:
        return redirect(url_for('login_bp.login'))

    # 🔒 PROTECCIÓN: Asegura que el cliente pertenece a la empresa
    client = Client.query.filter_by(id=client_id, company_id=company_id).filter(Client.archived_at.is_(None)).first()
    
    if not client:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('client_bp.list_clients'))

    client.archived_at = utcnow()
    db.session.commit()
    flash(f'Cliente "{client.name}" enviado a la papelera', 'info')
    return redirect(url_for('client_bp.list_clients'))


@client_bp.route('/<int:client_id>')
def client_detail(client_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    selected_currency = session.get('selected_currency', 'DOP')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    exchange = ExchangeRate.query.filter_by(company_id=company_id, currency_code=selected_currency).first() if selected_currency != 'DOP' else None
    conversion_rate = exchange_rate(exchange.rate if exchange else 1)
    currency_symbol = exchange.symbol if exchange else 'RD$'
    client = Client.query.filter_by(id=client_id, company_id=company_id, archived_at=None).first()
    
    if not client:
        flash('Cliente no encontrado.', 'danger')
        return redirect(url_for('client_bp.list_clients'))

    can_sales = bool(user and user.has_permission('sales.view'))
    can_returns = bool(user and user.has_permission('sales.returns'))

    # Los datos comerciales se muestran solo a perfiles autorizados para ventas.
    raw_sales = Sale.query.filter_by(
        client_id=client.id,
        company_id=company_id,
        status='COMPLETED'
    ).order_by(Sale.created_at.desc()).all() if can_sales else []

    # 3. REALIZAR LA CONVERSIÓN MATEMÁTICA
    processed_sales = []
    total_spent_converted = as_decimal(0)
    
    for sale in raw_sales:
        # Dividimos el monto de la base de datos entre la tasa de cambio
        monto_convertido = as_decimal(sale.total) / conversion_rate
        total_spent_converted += monto_convertido
        
        # Creamos un objeto temporal para el frontend
        processed_sales.append({
            'id': sale.id,
            'created_at': sale.created_at,
            'total': monto_convertido
        })

    total_sales = len(processed_sales)
    last_sale = processed_sales[0]['created_at'] if processed_sales else None
    can_finance = bool(user and user.has_permission('finance.receivables'))
    can_documents = bool(user and user.has_permission('company.documents'))
    receivable_balance = (sum((as_decimal(sale.balance) for sale in raw_sales), as_decimal(0)) / conversion_rate) if can_finance else None
    quotes = Sale.query.filter_by(client_id=client.id, company_id=company_id, status='QUOTATION').order_by(Sale.created_at.desc()).limit(20).all() if can_sales else []
    payments = CustomerPayment.query.filter_by(client_id=client.id, company_id=company_id).order_by(CustomerPayment.created_at.desc()).limit(20).all() if can_finance else []
    returns = SaleReturn.query.join(Sale, SaleReturn.sale_id == Sale.id).filter(
        SaleReturn.company_id == company_id, Sale.client_id == client.id
    ).order_by(SaleReturn.created_at.desc()).limit(20).all() if can_returns else []
    # Datos CRM defensivos: registros históricos incompletos no deben tumbar Cliente 360.
    interactions = sorted(
        list(client.interactions or []),
        key=lambda item: (item.created_at.replace(tzinfo=None) if item.created_at else datetime.min),
        reverse=True,
    )[:20]
    tasks = sorted(
        list(client.tasks or []),
        key=lambda item: (item.due_date.replace(tzinfo=None) if item.due_date else datetime.max),
    )[:20]
    documents = CompanyDocument.query.filter_by(company_id=company_id, entity_type='CLIENT', entity_id=client.id).order_by(CompanyDocument.created_at.desc()).all() if can_documents else []
    gift_cards = GiftCard.query.filter_by(company_id=company_id, client_id=client.id).order_by(GiftCard.created_at.desc()).limit(20).all()
    layaways = Layaway.query.filter_by(company_id=company_id, client_id=client.id).order_by(Layaway.created_at.desc()).limit(20).all()
    loyalty_transactions = LoyaltyTransaction.query.filter_by(company_id=company_id, client_id=client.id).order_by(LoyaltyTransaction.created_at.desc()).limit(20).all()
    credit_used = sum((as_decimal(sale.balance) for sale in raw_sales), as_decimal(0))
    credit_available = max(as_decimal(client.credit_limit) - credit_used, as_decimal(0)) if client.credit_enabled else as_decimal(0)

    return render_template(
        'clients/detail.html',
        client=client,
        sales=processed_sales, # Enviamos la lista ya convertida
        total_spent=total_spent_converted,
        total_sales=total_sales,
        last_sale=last_sale,
        user=user,
        currency_symbol=currency_symbol,
        selected_currency=selected_currency, conversion_rate=conversion_rate, receivable_balance=receivable_balance,
        quotes=quotes, payments=payments, returns=returns, interactions=interactions, tasks=tasks, documents=documents,
        can_sales=can_sales, can_returns=can_returns, can_finance=can_finance, can_documents=can_documents, today=date.today(),
        gift_cards=gift_cards, layaways=layaways, loyalty_transactions=loyalty_transactions, credit_used=credit_used, credit_available=credit_available
    )
