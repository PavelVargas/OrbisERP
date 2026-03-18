from flask import render_template, request, redirect, url_for, flash, session, current_app
from db import db
from models.sales.sales import Sale
from models.sales.sale_item import SaleItem
from models.products.products import Product
from models.category.category import Category
from models.client.client import Client
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.user.user import User
from models.divisas.divisas import ExchangeRate
from decimal import Decimal
from datetime import datetime

from .sales import sales_bp

def recalc_sale(sale):
    total_base = sum(item.quantity * item.price for item in sale.items)
    sale.total = Decimal(total_base).quantize(Decimal('0.01'))
    
    if sale.total > 0:
        base_imponible = sale.total / Decimal('1.18')
        sale.itbis = (sale.total - base_imponible).quantize(Decimal('0.01'))
    else:
        sale.itbis = Decimal('0.00')
    
    sale.subtotal = (sale.total - sale.itbis).quantize(Decimal('0.01'))

@sales_bp.route('/create', methods=['GET', 'POST'])
def create_sale():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        flash('Debes iniciar sesión para crear ventas', 'warning')
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    from models.company.company import Company
    company = Company.query.get(company_id)
    plan_limits = company.get_plan_limits()
    current_usage = company.get_current_month_usage()

    user_warehouse_id = user.warehouse_id if user else None

    # --- LÓGICA DE VENTA PENDIENTE ---
    current_id = session.get('current_sale_id')
    sale = None
    if current_id:
        sale = Sale.query.filter_by(id=current_id, company_id=company_id, user_id=user_id).first()
        if sale and sale.status not in ['PENDING']:
            sale = None
            session.pop('current_sale_id', None)

    if not sale:
        sale = Sale.query.filter_by(status='PENDING', user_id=user_id, company_id=company_id).first()

    if not sale:
        sale = Sale(status='PENDING', user_id=user_id, company_id=company_id, created_at=datetime.now())
        db.session.add(sale)
        db.session.commit()

    session['current_sale_id'] = sale.id

    # --- PROCESAR ESCANEO (POST) ---
    if request.method == 'POST':
        if current_usage >= plan_limits['max_monthly_invoices']:
            flash(f'Límite de facturación alcanzado ({plan_limits["max_monthly_invoices"]}).', 'danger')
            return redirect(url_for('sales_bp.create_sale'))

        barcode = request.form.get('search')
        if barcode:
            product = Product.query.filter_by(company_id=company_id, sku=barcode, status=True).first()
            if product:
                w_id = user_warehouse_id or (Warehouse.query.filter_by(company_id=company_id, status=True).first().id if Warehouse.query.filter_by(company_id=company_id, status=True).first() else None)
                if w_id:
                    item = SaleItem.query.filter_by(sale_id=sale.id, product_id=product.id, warehouse_id=w_id).first()
                    if item:
                        item.quantity += 1
                    else:
                        item = SaleItem(sale_id=sale.id, product_id=product.id, warehouse_id=w_id, quantity=1, price=product.price)
                        db.session.add(item)
                    recalc_sale(sale)
                    db.session.commit()
                else:
                    flash('Error: No hay almacenes configurados', 'danger')
            else:
                flash(f'Producto {barcode} no encontrado', 'warning')
        return redirect(url_for('sales_bp.create_sale'))

    selected_currency = session.get('selected_currency', 'DOP')
    rate_row = ExchangeRate.query.filter_by(currency_code=selected_currency).first()
    
    currency_symbol = rate_row.symbol if rate_row else 'RD$'
    # Aseguramos que conversion_rate sea Decimal para evitar errores de tipo con sale.total
    conversion_rate = Decimal(str(rate_row.rate)) if rate_row else Decimal('1.0')

    categories = Category.query.filter_by(company_id=company_id).order_by(Category.name.asc()).all()
    clients = Client.query.filter_by(company_id=company_id).order_by(Client.name.asc()).all()

    return render_template(
        'sales/create_sales.html',
        sale=sale, 
        categories=categories, 
        clients=clients, 
        user=user,
        plan_limits=plan_limits, 
        current_usage=current_usage,
        current_currency=selected_currency, 
        currency_symbol=currency_symbol,
        conversion_rate=conversion_rate
    )

@sales_bp.route('/assign-client', methods=['POST'])
def assign_client():
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()
    client_id = request.form.get('client_id', type=int)
    
    if not client_id:
        flash('Debes seleccionar un cliente', 'warning')
        return redirect(url_for('sales_bp.create_sale'))

    client = Client.query.filter_by(id=client_id, company_id=company_id).first_or_404()
    sale.client_id = client.id
    db.session.commit()

    flash(f'Cliente "{client.name}" asignado', 'success')
    return redirect(url_for('sales_bp.create_sale'))

@sales_bp.route('/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    user_id = session.get('user_id')

    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()
    
    if sale.user_id != user_id:
        flash('No tienes permiso para modificar esta venta', 'danger')
        return redirect(url_for('sales_bp.list_sales'))

    qty = int(request.form['qty'])
    warehouse_id = int(request.form['warehouse_id'])
    
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    warehouse = Warehouse.query.filter_by(id=warehouse_id, company_id=company_id).first_or_404()

    stock = WarehouseStock.query.filter_by(product_id=product.id, warehouse_id=warehouse.id).first()
    if not stock or stock.quantity < qty:
        flash(f'Stock insuficiente en {warehouse.name}', 'danger')
        return redirect(url_for('sales_bp.create_sale'))

    item = SaleItem.query.filter_by(sale_id=sale.id, product_id=product.id, warehouse_id=warehouse.id).first()

    if item:
        item.quantity += qty
    else:
        item = SaleItem(sale_id=sale.id, product_id=product.id, warehouse_id=warehouse.id, quantity=qty, price=product.price)
        db.session.add(item)

    recalc_sale(sale)
    db.session.commit()
    return redirect(url_for('sales_bp.create_sale'))

@sales_bp.route('/remove-item/<int:item_id>', methods=['POST'])
def remove_item(item_id):
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()
    item = SaleItem.query.filter_by(id=item_id, sale_id=sale.id).first_or_404()
    
    db.session.delete(item)
    recalc_sale(sale)
    db.session.commit()
    
    flash('Producto eliminado', 'info')
    return redirect(url_for('sales_bp.create_sale'))