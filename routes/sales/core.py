from flask import render_template, request, redirect, url_for, flash, session, current_app, jsonify
from db import db
from models.sales.sales import Sale
from models.sales.sale_item import SaleItem
from models.products.products import Product
from models.category.category import Category
from models.client.client import Client
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.stock_transfer.stock_transfer import StockTransfer
from models.user.user import User
from models.divisas.divisas import ExchangeRate
from decimal import Decimal
from datetime import datetime
from sqlalchemy import or_, func
from .sales import sales_bp


def available_sale_stock(product_id, warehouse_id, company_id):
    stock = WarehouseStock.query.filter_by(
        product_id=product_id,
        warehouse_id=warehouse_id,
        company_id=company_id,
    ).first()
    reserved = db.session.query(func.coalesce(func.sum(StockTransfer.quantity), 0)).filter(
        StockTransfer.product_id == product_id,
        StockTransfer.from_warehouse_id == warehouse_id,
        StockTransfer.company_id == company_id,
        StockTransfer.status == 'PENDING',
    ).scalar()
    return max(int(stock.quantity or 0) - int(reserved or 0), 0) if stock else 0

def recalc_sale(sale):
    """Recalcula subtotales, ITBIS (18%) y total de la venta."""
    total_base = sum(item.quantity * item.price for item in sale.items)
    sale.total = Decimal(total_base).quantize(Decimal('0.01'))
    
    if sale.total > 0:
        # Cálculo basado en tasa estándar del 18%
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

    current_id = session.get('current_sale_id')
    sale = None
    
    if current_id:
        sale = Sale.query.filter_by(id=current_id, company_id=company_id, user_id=user_id).first()
        if sale and sale.status not in ['PENDING', 'QUOTATION', 'DRAFT']:
            sale = None
            session.pop('current_sale_id', None)

    if not sale:
        sale = Sale.query.filter_by(status='PENDING', user_id=user_id, company_id=company_id).first()

    if not sale:
        sale = Sale(status='PENDING', user_id=user_id, company_id=company_id, created_at=datetime.now())
        db.session.add(sale)
        db.session.commit()

    session['current_sale_id'] = sale.id
    
    db.session.refresh(sale)

    # --- LÓGICA DE ESCANEO / AGREGAR (POST) ---
    search_query = request.form.get('search', '').strip()
    if search_query:
        product = Product.query.filter_by(sku=search_query, company_id=company_id, status=True).first()
        
        if not product:
            product = Product.query.filter_by(name=search_query, company_id=company_id, status=True).first()

        if product:
            p_type = str(product.product_type.value if hasattr(product.product_type, 'value') else product.product_type).upper()
            is_service = p_type in ['SERVICE', 'SERVICIO']

            w_id = user.warehouse_id or (Warehouse.query.filter_by(company_id=company_id, status=True).first().id if Warehouse.query.filter_by(company_id=company_id, status=True).first() else None)
            
            if w_id:
                if not is_service:
                    if available_sale_stock(product.id, w_id, company_id) < 1:
                        flash(f'Sin stock disponible para {product.name}', 'danger')
                        return redirect(url_for('sales_bp.create_sale'))

                item = SaleItem.query.filter_by(sale_id=sale.id, product_id=product.id, warehouse_id=w_id).first()
                if item:
                    item.quantity += 1
                else:
                    item = SaleItem(sale_id=sale.id, product_id=product.id, warehouse_id=w_id, quantity=1, price=product.price)
                    db.session.add(item)
                
                recalc_sale(sale)
                db.session.commit()
                flash(f'{product.name} agregado.', 'success')
            else:
                flash('No hay almacenes configurados', 'danger')
        else:
            flash(f'No se encontró el producto "{search_query}"', 'warning')
            
    # --- DATOS PARA EL TEMPLATE ---
    selected_currency = session.get('selected_currency', 'DOP')
    rate_row = ExchangeRate.query.filter_by(currency_code=selected_currency).first()
    
    currency_symbol = rate_row.symbol if rate_row else 'RD$'
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

@sales_bp.route('/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    user_id = session.get('user_id')

    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()
    
    if sale.user_id != user_id:
        flash('No tienes permiso para modificar esta venta', 'danger')
        return redirect(url_for('sales_bp.list_sales'))

    qty = int(request.form.get('qty', 1))
    warehouse_id = int(request.form.get('warehouse_id'))
    
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    
    p_type = str(product.product_type.value if hasattr(product.product_type, 'value') else product.product_type).upper()
    is_service = p_type in ['SERVICE', 'SERVICIO']

    if not is_service:
        warehouse = Warehouse.query.filter_by(id=warehouse_id, company_id=company_id).first_or_404()
        if available_sale_stock(product.id, warehouse.id, company_id) < qty:
            flash(f'Stock insuficiente en {warehouse.name}', 'danger')
            return redirect(url_for('sales_bp.create_sale'))

    item = SaleItem.query.filter_by(sale_id=sale.id, product_id=product.id, warehouse_id=warehouse_id).first()

    if item:
        item.quantity += qty
    else:
        item = SaleItem(sale_id=sale.id, product_id=product.id, warehouse_id=warehouse_id, quantity=qty, price=product.price)
        db.session.add(item)

    recalc_sale(sale)
    db.session.commit()
    return redirect(url_for('sales_bp.create_sale'))

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

@sales_bp.route('/get_products')
def get_products():
    company_id = session.get('company_id')
    if not company_id:
        return jsonify([]), 401

    search_query = request.args.get('search', '').strip()
    query = Product.query.filter_by(company_id=company_id, status=True)

    if search_query:
        query = query.filter(
            (Product.name.ilike(f'%{search_query}%')) |
            (Product.sku.ilike(f'%{search_query}%'))
        )
    
    products = query.limit(50).all()
    
    results = []
    for p in products:
        p_type = str(p.product_type.value if hasattr(p.product_type, 'value') else p.product_type).upper()
        
        results.append({
            'id': p.id,
            'name': p.name,
            'price': float(p.price),
            'sku': p.sku,
            'category': p.category.name if p.category else 'General',
            'type': p_type,
            'image': url_for('static', filename=p.image_path) if p.image_path else None
        })
    
    return jsonify(results)
