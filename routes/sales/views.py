from flask import render_template, request, redirect, url_for, session, flash
from models.sales.sales import Sale
from models.user.user import User
from models.divisas.divisas import ExchangeRate
from datetime import datetime, timedelta
from decimal import Decimal
from db import db

from .sales import sales_bp

@sales_bp.route('/')
def list_sales():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    status_filter = request.args.get('status')
    
    # --- LÓGICA DE DIVISAS (IGUAL AL DASHBOARD) ---
    # 1. Intentamos obtener la moneda de la sesión, si no, usamos DOP
    selected_currency_code = session.get('selected_currency', 'DOP')
    
    # 2. Buscamos la tasa de esa moneda específica para esta empresa
    rate_row = ExchangeRate.query.filter_by(
        currency_code=selected_currency_code, 
        company_id=company_id
    ).first()
    
    if rate_row:
        currency_symbol = rate_row.symbol
        conversion_rate = Decimal(str(rate_row.rate))
    else:
        # Si la moneda de la sesión no existe para esta empresa, buscamos la primera disponible
        rate_row = ExchangeRate.query.filter_by(company_id=company_id).first()
        if rate_row:
            selected_currency_code = rate_row.currency_code
            currency_symbol = rate_row.symbol
            conversion_rate = Decimal(str(rate_row.rate))
        else:
            selected_currency_code = 'DOP'
            currency_symbol = 'RD$'
            conversion_rate = Decimal('1.0')

    # Obtenemos todas las divisas de la empresa para el dropdown/filtros
    currencies = ExchangeRate.query.filter_by(company_id=company_id).all()

    # --- LÓGICA DE LÍMITES Y PLAN ---
    if user.company:
        limits = user.company.get_plan_limits()
        usage = user.company.get_current_month_usage()
        plan_name = user.company.plan_name
    else:
        limits = {'max_monthly_invoices': 999999}
        usage = 0
        plan_name = "Sin Plan"
    
    # Filtro de Ventas
    query = Sale.query.filter_by(company_id=company_id)
    if user.role != 'admin' and user.company_id:
        query = query.filter_by(user_id=user_id)
        
    if status_filter:
        query = query.filter_by(status=status_filter)
        
    sales = query.order_by(Sale.created_at.desc()).all()
    
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
                           conversion_rate=conversion_rate)

@sales_bp.route('/<int:sale_id>')
def sale_detail(sale_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()
    
    # Misma lógica de divisa para el detalle
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

@sales_bp.route('/resume/<int:sale_id>')
def resume_sale(sale_id):
    company_id = session.get('company_id')
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()
    if sale.status not in ['PENDING', 'QUOTATION', 'DRAFT']:
        flash('No se puede reanudar', 'warning')
        return redirect(url_for('sales_bp.list_sales'))
    session['current_sale_id'] = sale.id
    return redirect(url_for('sales_bp.create_sale'))