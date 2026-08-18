from flask import render_template, request, redirect, url_for, session, flash
from models.sales.sales import Sale
from models.sales.sale_item import SaleItem
from models.products.products import Product
from models.client.client import Client
from models.user.user import User
from models.divisas.divisas import ExchangeRate
from datetime import datetime, timedelta
from decimal import Decimal
from db import db
from sqlalchemy import String, cast, or_

from .sales import sales_bp

@sales_bp.route('/')
def list_sales():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    status_filter = (request.args.get('status') or '').strip().upper()
    search_query = (request.args.get('search') or '').strip()
    seller_id = request.args.get('seller_id', type=int)
    payment_method = (request.args.get('payment_method') or '').strip().upper()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    min_total = request.args.get('min_total', type=float)
    max_total = request.args.get('max_total', type=float)
    
    selected_currency_code = session.get('selected_currency', 'DOP')
    rate_row = ExchangeRate.query.filter_by(
        currency_code=selected_currency_code, 
        company_id=company_id
    ).first()
    
    if rate_row:
        currency_symbol = rate_row.symbol
        conversion_rate = Decimal(str(rate_row.rate))
    else:
        rate_row = ExchangeRate.query.filter_by(company_id=company_id).first()
        if rate_row:
            selected_currency_code = rate_row.currency_code
            currency_symbol = rate_row.symbol
            conversion_rate = Decimal(str(rate_row.rate))
        else:
            selected_currency_code = 'DOP'
            currency_symbol = 'RD$'
            conversion_rate = Decimal('1.0')

    currencies = ExchangeRate.query.filter_by(company_id=company_id).all()

    if user.company:
        limits = user.company.get_plan_limits()
        usage = user.company.get_current_month_usage()
        plan_name = user.company.plan_name
    else:
        limits = {'max_monthly_invoices': 999999}
        usage = 0
        plan_name = "Sin Plan"
    
    query = Sale.query.filter_by(company_id=company_id)
    if user.role != 'admin' and user.company_id:
        query = query.filter_by(user_id=user_id)
        seller_id = user_id
    elif seller_id:
        query = query.filter_by(user_id=seller_id)
        
    valid_statuses = {'COMPLETED', 'QUOTATION', 'PENDING', 'CANCELLED', 'DRAFT'}
    if status_filter in valid_statuses:
        query = query.filter_by(status=status_filter)
    elif status_filter:
        status_filter = ''
    if payment_method in {'CASH', 'CARD', 'TRANSFER', 'CREDIT'}:
        query = query.filter_by(payment_method=payment_method)
    elif payment_method:
        payment_method = ''
    if search_query:
        term = f'%{search_query}%'
        query = query.filter(or_(
            cast(Sale.id, String).ilike(term),
            Sale.customer_name.ilike(term),
            Sale.client.has(Client.name.ilike(term)),
            Sale.user.has(User.name.ilike(term)),
            Sale.items.any(SaleItem.product.has(or_(Product.name.ilike(term), Product.sku.ilike(term)))),
        ))
    try:
        if date_from:
            query = query.filter(Sale.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        if date_to:
            query = query.filter(Sale.created_at < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        flash('El rango de fechas no es válido.', 'warning')
        date_from = date_to = ''
    if min_total is not None:
        query = query.filter(Sale.total >= Decimal(str(min_total)) * conversion_rate)
    if max_total is not None:
        query = query.filter(Sale.total <= Decimal(str(max_total)) * conversion_rate)
        
    sales = query.order_by(Sale.created_at.desc()).all()
    sellers = User.query.filter_by(company_id=company_id).order_by(User.name.asc()).all()
    filtered_total = sum((sale.total or Decimal('0')) for sale in sales) / conversion_rate
    
    return render_template('sales/list.html', 
                           sales=sales, 
                           current_status=status_filter, 
                           is_admin=(user.role == 'admin' or not user.company_id),
                           user=user,
                           limits=limits, 
                           usage=usage,
                           plan_name=plan_name,
                           currencies=currencies,
                           selected_currency=selected_currency_code,
                           currency_symbol=currency_symbol,
                           conversion_rate=conversion_rate,
                           sellers=sellers,
                           search_query=search_query,
                           selected_seller=seller_id,
                           selected_payment=payment_method,
                           date_from=date_from,
                           date_to=date_to,
                           min_total=min_total,
                           max_total=max_total,
                           filtered_total=filtered_total)

@sales_bp.route('/<int:sale_id>')
def sale_detail(sale_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()
    
    selected_currency = session.get('selected_currency', 'DOP')
    rate_row = ExchangeRate.query.filter_by(currency_code=selected_currency, company_id=company_id).first()
    
    if not rate_row:
        rate_row = ExchangeRate.query.filter_by(company_id=company_id).first()

    currency_symbol = rate_row.symbol if rate_row else 'RD$'
    conversion_rate = Decimal(str(rate_row.rate)) if rate_row else Decimal('1.0')
    currencies = ExchangeRate.query.filter_by(company_id=company_id).all()

    return render_template('sales/detail_sales.html', 
                           sale=sale, 
                           user=user,
                           currencies=currencies,
                           selected_currency=selected_currency,
                           currency_symbol=currency_symbol,
                           conversion_rate=conversion_rate)

@sales_bp.route('/set_currency/<currency_code>', methods=['POST'])
def set_currency(currency_code):
    company_id = session.get('company_id')
    rate = ExchangeRate.query.filter_by(currency_code=currency_code, company_id=company_id).first()
    
    if rate:
        session['selected_currency'] = currency_code
        flash(f'Moneda cambiada a {currency_code}', 'success')
    
    return redirect(request.referrer or url_for('sales_bp.list_sales'))

@sales_bp.route('/pending')
def pending_sales():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    cutoff = datetime.now() - timedelta(hours=24)
    sales = Sale.query.filter(Sale.status == 'PENDING', Sale.company_id == company_id, Sale.created_at >= cutoff).order_by(Sale.created_at.desc()).all()

    return render_template('sales/pending.html', sales=sales, user=user)

# ==========================================================
# RETOMAR VENTA FIJANDO CONTEXTO DE ITEMS DE BASE DE DATOS
# ==========================================================
@sales_bp.route('/resume/<int:sale_id>')
def resume_sale(sale_id):
    company_id = session.get('company_id')
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()
    
    # Permitir retomar si está en estados editables
    if sale.status not in ['PENDING', 'QUOTATION', 'DRAFT']:
        flash('Esta orden ya fue procesada o anulada y no puede modificarse.', 'warning')
        return redirect(url_for('sales_bp.list_sales'))
        
    # Cambiamos temporalmente el estado a 'DRAFT' o lo mantenemos para que la pantalla de facturación 
    # sepa que estamos modificando una venta existente con registros reales en la tabla interna de ítems.
    session['current_sale_id'] = sale.id
    
    # Forzar expiración o refresco en la sesión de SQLALchemy para evitar cargas cacheadas vacías
    db.session.refresh(sale)
    
    flash(f'Cargando registros de la Venta #{sale.id}', 'info')
    return redirect(url_for('sales_bp.create_sale'))
