from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import db
from models.products.products import Product
from models.stock_movement.stock_movement import StockMovement
from models.category.category import Category
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.user.user import User

stock_bp = Blueprint('stock_bp', __name__)

# =========================
# AJUSTAR STOCK DE UN PRODUCTO
# =========================
@stock_bp.route('/stock/adjust/<int:product_id>', methods=['GET', 'POST'])
def adjust_stock(product_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    # Seguridad: Producto debe pertenecer a la empresa
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    warehouses = Warehouse.query.filter_by(status=True, company_id=company_id).all()

    if request.method == 'POST':
        warehouse_id = int(request.form.get('warehouse_id'))
        movement_type = request.form.get('movement_type')  # IN / OUT
        quantity = int(request.form.get('quantity'))
        reason = request.form.get('reason')

        if quantity <= 0:
            flash('La cantidad debe ser mayor a 0', 'error')
            return redirect(request.url)

        # Seguridad: Almacén debe pertenecer a la empresa
        warehouse = Warehouse.query.filter_by(id=warehouse_id, company_id=company_id).first_or_404()

        stock = WarehouseStock.query.filter_by(
            product_id=product.id,
            warehouse_id=warehouse.id,
            company_id=company_id
        ).first()

        if not stock:
            stock = WarehouseStock(
                product_id=product.id,
                warehouse_id=warehouse.id,
                company_id=company_id,
                quantity=0
            )
            db.session.add(stock)

        if movement_type == 'OUT' and stock.quantity < quantity:
            flash('Stock insuficiente en el almacén', 'error')
            return redirect(request.url)

        if movement_type == 'IN':
            stock.quantity += quantity
        else:
            stock.quantity -= quantity

        movement = StockMovement(
            product_id=product.id,
            warehouse_id=warehouse.id,
            company_id=company_id,
            movement_type=movement_type,
            quantity=quantity,
            reason=reason,
            user=user
        )
        db.session.add(movement)
        db.session.commit()

        flash('Stock actualizado correctamente', 'success')
        return redirect(url_for('products_bp.list_products'))

    return render_template(
        'stock/adjust_stock.html',
        product=product,
        warehouses=warehouses,
        user=user
    )

# =========================
# HISTORIAL DE STOCK DE UN PRODUCTO
# =========================
@stock_bp.route('/stock/history/<int:product_id>')
def stock_history(product_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    
    movements = StockMovement.query.filter_by(product_id=product.id, company_id=company_id)\
        .order_by(StockMovement.created_at.desc()).all()
        
    return render_template(
        'stock/stock_history.html',
        product=product,
        movements=movements,
        user=user
    )

# =========================
# STOCK ACTUAL (TABLA DE INVENTARIO)
# =========================
@stock_bp.route('/stock')
def stock_actual():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    category_id = request.args.get('category_id', type=int)
    search = request.args.get('search', '')
    warehouse_id = request.args.get('warehouse_id', type=int)

    query = Product.query.filter_by(status=True, company_id=company_id)
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))

    products = query.order_by(Product.name.asc()).all()
    categories = Category.query.filter_by(status=True, company_id=company_id).all()
    warehouses = Warehouse.query.filter_by(status=True, company_id=company_id).all()

    stocks = {}
    for p in products:
        stocks[p.id] = {}
        for w in warehouses:
            ws = WarehouseStock.query.filter_by(
                product_id=p.id, 
                warehouse_id=w.id, 
                company_id=company_id
            ).first()
            stocks[p.id][w.id] = ws.quantity if ws else 0

    return render_template(
        'stock/stock_actual.html',
        products=products,
        categories=categories,
        warehouses=warehouses,
        stocks=stocks,
        category_id=category_id,
        search=search,
        warehouse_id=warehouse_id,
        user=user
    )

# =========================
# KARDEX GENERAL (MOVIMIENTOS)
# =========================
@stock_bp.route('/kardex')
def kardex_general():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    product_id = request.args.get('product_id', type=int)
    warehouse_id = request.args.get('warehouse_id', type=int)
    movement_type = request.args.get('movement_type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    query = StockMovement.query.join(Product).filter(StockMovement.company_id == company_id)

    if product_id:
        query = query.filter(StockMovement.product_id == product_id)
    if warehouse_id:
        query = query.filter(StockMovement.warehouse_id == warehouse_id)
    if movement_type in ['IN', 'OUT']:
        query = query.filter(StockMovement.movement_type == movement_type)
    if date_from:
        query = query.filter(StockMovement.created_at >= date_from)
    if date_to:
        query = query.filter(StockMovement.created_at <= date_to)

    movements = query.order_by(StockMovement.created_at.desc()).all()
    
    products = Product.query.filter_by(status=True, company_id=company_id).all()
    warehouses = Warehouse.query.filter_by(status=True, company_id=company_id).all()

    return render_template(
        'stock/kardex.html',
        movements=movements,
        products=products,
        warehouses=warehouses,
        product_id=product_id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        date_from=date_from,
        date_to=date_to,
        user=user
    )