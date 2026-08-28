from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request
from sqlalchemy import func, desc, or_
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
from models.backoffice import AppNotification, Expense, SaleReturn, SaleReturnItem, SupplierBill
from models.purchase.purchase_order import PurchaseOrder
from models.stock_transfer.stock_transfer import StockTransfer

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

    result = q.scalar() or 0
    returns_q = db.session.query(func.sum(SaleReturn.total_refund)).join(Sale, Sale.id == SaleReturn.sale_id).filter(
        SaleReturn.company_id == company_id, SaleReturn.status == 'COMPLETED'
    )
    if not is_admin:
        returns_q = returns_q.filter(Sale.user_id == user_id)
    if start_dt and end_dt:
        returns_q = returns_q.filter(SaleReturn.created_at >= start_dt, SaleReturn.created_at < end_dt)
    elif start_dt:
        returns_q = returns_q.filter(SaleReturn.created_at >= start_dt, SaleReturn.created_at < start_dt + timedelta(days=1))
    return float(result) - float(returns_q.scalar() or 0)


def calculate_growth(current, previous):

    curr = float(current)
    prev = float(previous)

    if prev == 0:
        return 100.0 if curr > 0 else 0.0

    return ((curr - prev) / prev) * 100


def get_daily_sales_series(company_id, is_admin, user_id, start_dt, end_dt):
    """Return net daily revenue with two grouped queries instead of N queries."""
    sale_day = func.date(Sale.created_at)
    sales_query = db.session.query(sale_day.label('day'), func.sum(Sale.total).label('amount')).filter(
        Sale.company_id == company_id, Sale.status == 'COMPLETED',
        Sale.created_at >= start_dt, Sale.created_at < end_dt,
    )
    if not is_admin:
        sales_query = sales_query.filter(Sale.user_id == user_id)
    sales_map = {row.day: float(row.amount or 0) for row in sales_query.group_by(sale_day).all()}

    return_day = func.date(SaleReturn.created_at)
    returns_query = db.session.query(return_day.label('day'), func.sum(SaleReturn.total_refund).label('amount')).join(
        Sale, Sale.id == SaleReturn.sale_id
    ).filter(
        SaleReturn.company_id == company_id, SaleReturn.status == 'COMPLETED',
        SaleReturn.created_at >= start_dt, SaleReturn.created_at < end_dt,
    )
    if not is_admin:
        returns_query = returns_query.filter(Sale.user_id == user_id)
    returns_map = {row.day: float(row.amount or 0) for row in returns_query.group_by(return_day).all()}

    labels, values = [], []
    cursor = start_dt
    while cursor < end_dt:
        current_day = cursor.date()
        labels.append(cursor.strftime('%d %b'))
        values.append(sales_map.get(current_day, 0) - returns_map.get(current_day, 0))
        cursor += timedelta(days=1)
    return labels, values


@dashboard_bp.route('/dashboard')
def dashboard():

    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = db.session.get(User, user_id)

    if not user:
        session.clear()
        return redirect(url_for('login_bp.login'))

    company_id = session.get('company_id') or user.company_id
    company = db.session.get(Company, company_id)

    if not company:
        return redirect(url_for('company_bp.create_company'))

    # -------- DIVISA --------

    selected_currency = session.get('selected_currency', 'DOP')
    rate = float(ExchangeRate.get_rate_or_default(selected_currency, company_id))

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
    can_receivables = user.has_permission('finance.receivables')
    can_payables = user.has_permission('finance.payables')
    can_expenses = user.has_permission('finance.expenses')
    can_costs = user.has_permission('products.costs')
    can_stock = user.has_permission('stock.view')
    can_purchases = user.has_permission('purchases.view')

    now_dt = datetime.now()

    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    yesterday_start = today_start - timedelta(days=1)

    start_current_month = today_start.replace(day=1)

    start_last_month = (start_current_month - timedelta(days=1)).replace(day=1)
    period_days = request.args.get('period', default=30, type=int)
    if period_days not in {7, 30, 90}:
        period_days = 30

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

    completed_sales_query = Sale.query.filter_by(company_id=company_id, status='COMPLETED')
    pending_sales_query = Sale.query.filter_by(company_id=company_id, status='PENDING')
    if not is_admin:
        completed_sales_query = completed_sales_query.filter(Sale.user_id == user_id)
        pending_sales_query = pending_sales_query.filter(Sale.user_id == user_id)
    total_tickets_count = completed_sales_query.count()
    pending_count = pending_sales_query.count()
    quote_query = Sale.query.filter_by(company_id=company_id, status='QUOTATION')
    if not is_admin:
        quote_query = quote_query.filter(Sale.user_id == user_id)
    quote_count = quote_query.count()

    low_stock_products = db.session.query(WarehouseStock).filter(
        WarehouseStock.company_id == company_id,
        WarehouseStock.quantity <= 5
    ).count() if can_stock else 0

    receivables_query = db.session.query(func.coalesce(func.sum(Sale.balance), 0)).filter(
        Sale.company_id == company_id, Sale.status == 'COMPLETED', Sale.balance > 0
    )
    if not is_admin:
        receivables_query = receivables_query.filter(Sale.user_id == user_id)
    receivables_total = receivables_query.scalar() if can_receivables else 0
    payables_total = db.session.query(func.coalesce(func.sum(SupplierBill.amount - SupplierBill.paid_amount), 0)).filter(
        SupplierBill.company_id == company_id, SupplierBill.status != 'PAID'
    ).scalar() if can_payables else 0
    expenses_month = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.company_id == company_id, Expense.expense_date >= start_current_month.date()
    ).scalar() if can_expenses else 0
    inventory_value = db.session.query(func.coalesce(func.sum(WarehouseStock.quantity * Product.cost), 0)).join(
        Product, Product.id == WarehouseStock.product_id
    ).filter(WarehouseStock.company_id == company_id).scalar() if can_costs and can_stock else 0
    inventory_units = db.session.query(func.coalesce(func.sum(WarehouseStock.quantity), 0)).filter(
        WarehouseStock.company_id == company_id
    ).scalar() if can_stock else 0
    cogs_query = db.session.query(func.coalesce(func.sum(SaleItem.quantity * Product.cost), 0)).select_from(SaleItem).join(
        Sale, Sale.id == SaleItem.sale_id
    ).join(Product, Product.id == SaleItem.product_id).filter(
        Sale.company_id == company_id, Sale.status == 'COMPLETED', Sale.created_at >= start_current_month
    )
    if not is_admin:
        cogs_query = cogs_query.filter(Sale.user_id == user_id)
    if can_costs:
        returned_cost_query = db.session.query(
            func.coalesce(func.sum(SaleReturnItem.quantity * Product.cost), 0)
        ).select_from(SaleReturnItem).join(
            SaleReturn, SaleReturn.id == SaleReturnItem.return_id
        ).join(Product, Product.id == SaleReturnItem.product_id).join(
            Sale, Sale.id == SaleReturn.sale_id
        ).filter(
            SaleReturn.company_id == company_id,
            SaleReturn.status == 'COMPLETED',
            SaleReturn.created_at >= start_current_month,
        )
        if not is_admin:
            returned_cost_query = returned_cost_query.filter(Sale.user_id == user_id)
        returned_cost = returned_cost_query.scalar() or 0
        net_cogs = max(float(cogs_query.scalar() or 0) - float(returned_cost), 0)
        gross_profit = float(revenue_this_month or 0) - net_cogs
        operating_result_base = gross_profit - float(expenses_month or 0) if can_expenses else gross_profit
        margin_percent = (gross_profit / float(revenue_this_month) * 100) if float(revenue_this_month or 0) > 0 else 0
    else:
        gross_profit = None
        operating_result_base = None
        margin_percent = None
    sales_count_query = Sale.query.filter(
        Sale.company_id == company_id, Sale.status == 'COMPLETED', Sale.created_at >= start_current_month
    )
    if not is_admin:
        sales_count_query = sales_count_query.filter(Sale.user_id == user_id)
    sales_count_month = sales_count_query.count()
    returns_query = SaleReturn.query.join(Sale, Sale.id == SaleReturn.sale_id).filter(
        SaleReturn.company_id == company_id, SaleReturn.created_at >= start_current_month
    )
    if not is_admin:
        returns_query = returns_query.filter(Sale.user_id == user_id)
    returns_month = returns_query.count()
    pending_transfers = StockTransfer.query.filter_by(company_id=company_id, status='PENDING').count()
    overdue_payables = SupplierBill.query.filter(
        SupplierBill.company_id == company_id, SupplierBill.status != 'PAID',
        SupplierBill.due_date.isnot(None), SupplierBill.due_date < today_start.date(),
    ).count() if can_payables else 0
    unread_notifications = AppNotification.query.filter(
        AppNotification.company_id == company_id, AppNotification.read_at.is_(None),
        or_(AppNotification.user_id.is_(None), AppNotification.user_id == user_id)
    ).count()
    payment_query = db.session.query(Sale.payment_method, func.sum(Sale.total)).filter(
        Sale.company_id == company_id, Sale.status == 'COMPLETED', Sale.created_at >= start_current_month
    )
    if not is_admin:
        payment_query = payment_query.filter(Sale.user_id == user_id)
    payment_rows = payment_query.group_by(Sale.payment_method).all()
    payment_labels = [row[0] or 'OTRO' for row in payment_rows]
    payment_values = [float(row[1] or 0) / rate for row in payment_rows]
    recent_purchases = PurchaseOrder.query.filter_by(company_id=company_id).order_by(
        PurchaseOrder.created_at.desc()
    ).limit(4).all() if can_purchases else []

    # -------- GRÁFICO POR PERIODO --------
    chart_start = today_start - timedelta(days=period_days - 1)
    chart_labels, chart_values_base = get_daily_sales_series(
        company_id, is_admin, user_id, chart_start, today_start + timedelta(days=1)
    )
    chart_values = [value / rate for value in chart_values_base]

    # -------- VENTAS RECIENTES --------

    recent_sales_query = Sale.query.filter_by(company_id=company_id)
    if not is_admin:
        recent_sales_query = recent_sales_query.filter(Sale.user_id == user_id)
    recent_sales = recent_sales_query.order_by(Sale.created_at.desc()).limit(6).all()

    for sale in recent_sales:
        sale.converted_total = float(sale.total) / rate

    # -------- PRODUCTOS MAS VENDIDOS --------

    top_products_query = db.session.query(
        Product.name, Product.sku, Product.image_path,
        func.sum(SaleItem.quantity).label('qty'),
        func.sum(SaleItem.quantity * SaleItem.price).label('revenue')
    ).join(SaleItem).join(Sale).filter(
        Sale.company_id == company_id,
        Sale.status == 'COMPLETED'
    )
    if not is_admin:
        top_products_query = top_products_query.filter(Sale.user_id == user_id)
    top_products = top_products_query.group_by(
        Product.id,
        Product.name, Product.sku, Product.image_path
    ).order_by(desc('qty')).limit(5).all()

    total_clients_count = Client.query.filter_by(company_id=company_id).filter(Client.archived_at.is_(None)).count()
    recent_clients = Client.query.filter_by(company_id=company_id).filter(Client.archived_at.is_(None)).order_by(Client.created_at.desc()).limit(5).all()

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
        quote_count=quote_count,
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

        conversion_rate=rate,
        selected_currency=selected_currency,
        receivables_total=float(receivables_total or 0) / rate,
        payables_total=float(payables_total or 0) / rate,
        expenses_month=float(expenses_month or 0) / rate,
        inventory_value=float(inventory_value or 0) / rate,
        returns_month=returns_month,
        pending_transfers=pending_transfers,
        unread_notifications=unread_notifications,
        payment_labels=payment_labels,
        payment_values=payment_values,
        recent_purchases=recent_purchases,
        period_days=period_days,
        sales_count_month=sales_count_month,
        inventory_units=int(inventory_units or 0),
        gross_profit=gross_profit / rate if gross_profit is not None else None,
        margin_percent=margin_percent,
        net_result=operating_result_base / rate if operating_result_base is not None else None,
        overdue_payables=overdue_payables,
        can_receivables=can_receivables,
        can_payables=can_payables,
        can_expenses=can_expenses,
        can_costs=can_costs,
        can_stock=can_stock,
        can_purchases=can_purchases,
    )


@dashboard_bp.route('/api/dashboard/realtime-stats')
def realtime_stats():

    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return jsonify({"error": "Unauthorized"}), 401

    selected_currency = session.get('selected_currency', 'DOP')

    rate = float(ExchangeRate.get_rate_or_default(selected_currency, company_id))

    user = db.session.get(User, user_id)

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


    pending_query = Sale.query.filter_by(company_id=company_id, status='PENDING')
    if not is_admin:
        pending_query = pending_query.filter(Sale.user_id == user_id)

    return jsonify({

        "sales_today": sales_today_base / rate,

        "pending_count": pending_query.count(),

        "low_stock_count": db.session.query(WarehouseStock).filter(
            WarehouseStock.company_id == company_id,
            WarehouseStock.quantity <= 5
        ).count() if user.has_permission('stock.view') else 0,

        "receipt_status": db.session.get(Company, company_id).receipt_status
    })

TABLET_MODE_COOKIE = 'orbis_ui_mode'
LEGACY_TABLET_MODE_COOKIE = 'orbis_tablet_mode'
TABLET_MODE_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def _tablet_preference_response(response, enabled):
    response.set_cookie(
        TABLET_MODE_COOKIE,
        'tablet' if enabled else 'desktop',
        max_age=TABLET_MODE_COOKIE_MAX_AGE,
        path='/',
        samesite='Lax',
        secure=request.is_secure,
        httponly=False,
    )
    response.set_cookie(
        LEGACY_TABLET_MODE_COOKIE,
        '1' if enabled else '0',
        max_age=TABLET_MODE_COOKIE_MAX_AGE,
        path='/',
        samesite='Lax',
        secure=request.is_secure,
        httponly=False,
    )
    return response


@dashboard_bp.route('/tablet/enable')
def enable_tablet_mode():
    # Tablet mode is a durable application profile. The Flask session drives
    # server rendering while the dedicated preference cookie survives every
    # module navigation and lets app.py restore the profile if a route happens
    # to rebuild non-security session context.
    session['tablet_mode'] = True
    session.modified = True
    response = redirect(url_for('launchpad_bp.launchpad'))
    return _tablet_preference_response(response, True)


@dashboard_bp.route('/tablet/disable')
def disable_tablet_mode():
    session.pop('tablet_mode', None)
    session.modified = True
    response = redirect(url_for('dashboard_bp.dashboard'))
    return _tablet_preference_response(response, False)
