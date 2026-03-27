from flask import Blueprint, render_template, session, redirect, url_for, jsonify
from sqlalchemy import func, desc
from datetime import datetime, timedelta

from models.user.user import User
from models.company.company import Company 
from models.sales.sales import Sale
from models.sales.sale_item import SaleItem
from models.products.products import Product
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.divisas.divisas import ExchangeRate
from db import db
from models.client.client import Client

dashboard_bp = Blueprint('dashboard_bp', __name__)

# --- Función Auxiliar Global ---
def get_sales_data(company_id, is_admin, user_id, start_dt=None, end_dt=None):

    q = db.session.query(func.sum(Sale.total)).filter(
        Sale.company_id == company_id,
        Sale.status == 'COMPLETED'
    )

    if not is_admin:
        q = q.filter(Sale.user_id == user_id)

    if start_dt and end_dt:
        q = q.filter(Sale.created_at >= start_dt, Sale.created_at < end_dt)

    elif start_dt:
        next_day = start_dt + timedelta(days=1)
        q = q.filter(Sale.created_at >= start_dt, Sale.created_at < next_day)

    result = q.scalar()

    return float(result) if result is not None else 0.0


def calculate_growth(current, previous):

    curr = float(current)
    prev = float(previous)

    if prev == 0:
        return 100.0 if curr > 0 else 0.0

    return ((curr - prev) / prev) * 100


@dashboard_bp.route('/dashboard')
def dashboard():

    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)

    if not user:
        session.clear()
        return redirect(url_for('login_bp.login'))

    company_id = session.get('company_id') or user.company_id
    company = Company.query.get(company_id)

    if not company:
        return redirect(url_for('company_bp.create_company'))

    # -------- DIVISA --------

    selected_currency = session.get('selected_currency', 'DOP')
    rate = float(ExchangeRate.get_rate(selected_currency, company_id))

    # -------- PLAN Y LIMITES --------

    plan_limits = company.get_plan_limits()

    invoices_usage = float(company.get_current_month_usage() or 0)
    invoices_limit = float(plan_limits.get('max_monthly_invoices', 1))

    inv_percent = min((invoices_usage / invoices_limit) * 100, 100) if invoices_limit > 0 else 0

    users_count = User.query.filter_by(company_id=company_id).count()
    users_limit = plan_limits.get('max_users', 1)

    users_percent = min((users_count / users_limit) * 100, 100)

    wares_count = Warehouse.query.filter_by(company_id=company_id).count()
    wares_limit = plan_limits.get('max_warehouses', 1)

    wares_percent = min((wares_count / wares_limit) * 100, 100)

    is_admin = user.role in ['admin', 'superadmin']

    now_dt = datetime.now()

    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    yesterday_start = today_start - timedelta(days=1)

    start_current_month = today_start.replace(day=1)

    start_last_month = (start_current_month - timedelta(days=1)).replace(day=1)

    # -------- INGRESOS --------

    total_revenue_base = get_sales_data(company_id, is_admin, user_id)
    total_revenue = total_revenue_base / rate

    revenue_this_month = get_sales_data(
        company_id,
        is_admin,
        user_id,
        start_current_month,
        now_dt + timedelta(seconds=1)
    )

    revenue_last_month = get_sales_data(
        company_id,
        is_admin,
        user_id,
        start_last_month,
        start_current_month
    )

    revenue_growth = calculate_growth(revenue_this_month, revenue_last_month)

    sales_today_base = get_sales_data(company_id, is_admin, user_id, start_dt=today_start)

    sales_today = sales_today_base / rate

    sales_yesterday = get_sales_data(company_id, is_admin, user_id, yesterday_start, today_start)

    sales_growth = calculate_growth(sales_today_base, sales_yesterday)

    avg_res = db.session.query(func.avg(Sale.total)).filter(
        Sale.company_id == company_id,
        Sale.status == 'COMPLETED'
    ).filter(Sale.user_id == user_id if not is_admin else True).scalar()

    avg_ticket = (float(avg_res) if avg_res else 0.0) / rate

    total_tickets_count = Sale.query.filter_by(
        company_id=company_id,
        status='COMPLETED'
    ).count()

    pending_count = Sale.query.filter_by(
        company_id=company_id,
        status='PENDING'
    ).count()

    low_stock_products = db.session.query(WarehouseStock).filter(
        WarehouseStock.company_id == company_id,
        WarehouseStock.quantity <= 5
    ).count()

    # -------- GRAFICO 7 DIAS --------

    chart_labels = []
    chart_values = []

    for i in range(6, -1, -1):

        day_dt = today_start - timedelta(days=i)

        chart_labels.append(day_dt.strftime('%d/%m'))

        val_base = get_sales_data(company_id, is_admin, user_id, start_dt=day_dt)

        chart_values.append(val_base / rate)

    # -------- VENTAS RECIENTES --------

    recent_sales = Sale.query.filter_by(
        company_id=company_id
    ).order_by(Sale.created_at.desc()).limit(10).all()

    for sale in recent_sales:
        sale.converted_total = float(sale.total) / rate

    # -------- PRODUCTOS MAS VENDIDOS --------

    top_products = db.session.query(
        Product.name,
        func.sum(SaleItem.quantity).label('qty')
    ).join(SaleItem).join(Sale).filter(
        Sale.company_id == company_id,
        Sale.status == 'COMPLETED'
    ).group_by(
        Product.id,
        Product.name
    ).order_by(desc('qty')).limit(5).all()
    
    total_clients_count = Client.query.filter_by(company_id=company_id).count()
    recent_clients = Client.query.filter_by(company_id=company_id).order_by(Client.created_at.desc()).limit(5).all()

    return render_template(
        'dashboard/dashboard.html',

        user=user,
        company=company,
        is_admin=is_admin,

        total_revenue=total_revenue,
        revenue_this_month=revenue_this_month,
        revenue_growth=revenue_growth,

        sales_today=sales_today,
        sales_growth=sales_growth,

        avg_ticket=avg_ticket,

        total_tickets_count=total_tickets_count,
        pending_count=pending_count,
        low_stock_products=low_stock_products,
        total_clients_count=total_clients_count,
        recent_clients=recent_clients,
        chart_labels=chart_labels,
        chart_values=chart_values,

        recent_sales=recent_sales,

        plan_name=company.plan_name,

        invoices_usage=invoices_usage,
        invoices_limit=invoices_limit,
        inv_percent=inv_percent,

        users_count=users_count,
        users_limit=users_limit,
        users_percent=users_percent,

        wares_count=wares_count,
        wares_limit=wares_limit,
        wares_percent=wares_percent,

        now=now_dt,

        top_products=top_products,

        conversion_rate=rate
    )


@dashboard_bp.route('/api/dashboard/realtime-stats')
def realtime_stats():

    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return jsonify({"error": "Unauthorized"}), 401

    selected_currency = session.get('selected_currency', 'DOP')

    rate = float(ExchangeRate.get_rate(selected_currency, company_id))

    user = User.query.get(user_id)

    is_admin = user.role in ['admin', 'superadmin']

    today_start = datetime.now().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    sales_today_base = get_sales_data(
        company_id,
        is_admin,
        user_id,
        start_dt=today_start
    )
    

    return jsonify({

        "sales_today": sales_today_base / rate,

        "pending_count": Sale.query.filter_by(
            company_id=company_id,
            status='PENDING'
        ).count(),

        "low_stock_count": db.session.query(WarehouseStock).filter(
            WarehouseStock.company_id == company_id,
            WarehouseStock.quantity <= 5
        ).count(),

        "receipt_status": Company.query.get(company_id).receipt_status
    })
    
@dashboard_bp.route('/tablet/enable')
def enable_tablet_mode():
    session['tablet_mode'] = True
    return redirect(url_for('launchpad_bp.index')) 

@dashboard_bp.route('/tablet/disable')
def disable_tablet_mode():
    session.pop('tablet_mode', None)
    return redirect(url_for('dashboard_bp.dashboard'))