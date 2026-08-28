from flask import render_template, request, redirect, url_for, session, flash
from models.sales.sales import Sale
from models.sales.sale_item import SaleItem
from models.products.products import Product
from models.client.client import Client
from models.user.user import User
from models.divisas.divisas import ExchangeRate
from models.retail import WarrantyClaim
from datetime import datetime, timedelta
from decimal import Decimal
from db import db
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import selectinload

from services.numeric import bounded_decimal, finite_decimal
from services.validation import BusinessRuleError

from .sales import sales_bp
from .access import can_view_all_sales, editable_sales_query, visible_sales_query

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
    min_total_raw = (request.args.get('min_total') or '').strip()
    max_total_raw = (request.args.get('max_total') or '').strip()
    min_total = max_total = None
    try:
        if min_total_raw:
            min_total = bounded_decimal(
                min_total_raw, field_name='Total mínimo', places=2,
                minimum='0', maximum='9999999999.99',
            )
        if max_total_raw:
            max_total = bounded_decimal(
                max_total_raw, field_name='Total máximo', places=2,
                minimum='0', maximum='9999999999.99',
            )
        if min_total is not None and max_total is not None and min_total > max_total:
            raise BusinessRuleError('El total mínimo no puede superar el total máximo.')
    except BusinessRuleError as exc:
        flash(str(exc), 'warning')
        min_total = max_total = None
    
    selected_currency_code = session.get('selected_currency', 'DOP')
    rate_row = ExchangeRate.query.filter_by(
        currency_code=selected_currency_code, 
        company_id=company_id
    ).first()
    
    if not rate_row:
        rate_row = ExchangeRate.query.filter_by(company_id=company_id).first()
        if rate_row:
            selected_currency_code = rate_row.currency_code
    if rate_row:
        currency_symbol = rate_row.symbol
        try:
            conversion_rate = finite_decimal(rate_row.rate, field_name='Tasa de conversión')
            if conversion_rate <= 0:
                raise BusinessRuleError('La tasa de conversión debe ser mayor que cero.')
        except BusinessRuleError:
            conversion_rate = Decimal('1')
    else:
        selected_currency_code = 'DOP'
        currency_symbol = 'RD$'
        conversion_rate = Decimal('1')

    currencies = ExchangeRate.query.filter_by(company_id=company_id).all()

    if user.company:
        limits = user.company.get_plan_limits()
        usage = user.company.get_current_month_usage()
        plan_name = user.company.plan_name
    else:
        limits = {'max_monthly_invoices': 999999}
        usage = 0
        plan_name = "Sin Plan"
    
    query = visible_sales_query(company_id, user_id)
    if not can_view_all_sales(user):
        seller_id = user_id
    elif seller_id:
        query = query.filter_by(user_id=seller_id)
        
    valid_statuses = {'COMPLETED', 'QUOTATION', 'PENDING', 'CANCELLED', 'DRAFT', 'LAYAWAY'}
    if status_filter in valid_statuses:
        query = query.filter_by(status=status_filter)
    elif status_filter:
        status_filter = ''
    if payment_method in {'CASH', 'CARD', 'TRANSFER', 'CREDIT', 'MIXED', 'LAYAWAY'}:
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
        query = query.filter(Sale.total >= min_total * conversion_rate)
    if max_total is not None:
        query = query.filter(Sale.total <= max_total * conversion_rate)
        
    sales = query.options(
        selectinload(Sale.items).selectinload(SaleItem.warehouse)
    ).order_by(Sale.created_at.desc()).all()
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
                           filtered_total=filtered_total,
                           today=datetime.now().date())

@sales_bp.route('/<int:sale_id>')
def sale_detail(sale_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    sale = visible_sales_query(company_id, user_id).filter_by(id=sale_id).first_or_404()
    
    selected_currency = session.get('selected_currency', 'DOP')
    rate_row = ExchangeRate.query.filter_by(currency_code=selected_currency, company_id=company_id).first()
    
    if not rate_row:
        rate_row = ExchangeRate.query.filter_by(company_id=company_id).first()

    currency_symbol = rate_row.symbol if rate_row else 'RD$'
    try:
        conversion_rate = finite_decimal(rate_row.rate, field_name='Tasa de conversión') if rate_row else Decimal('1')
        if conversion_rate <= 0:
            raise BusinessRuleError('La tasa de conversión debe ser mayor que cero.')
    except BusinessRuleError:
        conversion_rate = Decimal('1')
    currencies = ExchangeRate.query.filter_by(company_id=company_id).all()
    claims = WarrantyClaim.query.join(SaleItem, WarrantyClaim.sale_item_id == SaleItem.id).filter(
        WarrantyClaim.company_id == company_id,
        SaleItem.sale_id == sale.id,
    ).order_by(WarrantyClaim.opened_at.desc()).all()
    claims_by_item = {}
    for claim in claims:
        claims_by_item.setdefault(claim.sale_item_id, []).append(claim)
    warranty_until_by_item = {
        item.id: (sale.created_at + timedelta(days=max(int(item.product.warranty_days or 30), 1))).date()
        for item in sale.items
    }

    return render_template('sales/detail_sales.html', 
                           sale=sale, 
                           user=user,
                           currencies=currencies,
                           selected_currency=selected_currency,
                           currency_symbol=currency_symbol,
                           conversion_rate=conversion_rate,
                           claims_by_item=claims_by_item,
                           warranty_until_by_item=warranty_until_by_item)

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
    # Compatibilidad: los pendientes se consultan en la vista única de Ventas.
    return redirect(url_for('sales_bp.list_sales', status='PENDING'))


# ==========================================================
# RETOMAR VENTA FIJANDO CONTEXTO DE ITEMS DE BASE DE DATOS
# ==========================================================
@sales_bp.route('/resume/<int:sale_id>')
def resume_sale(sale_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    sale = editable_sales_query(company_id, user_id).filter_by(id=sale_id).first_or_404()
    
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
