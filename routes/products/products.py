from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from models.products.products import Product, ProductType # <--- Importar ProductType
from models.category.category import Category
from models.user.user import User
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.divisas.divisas import ExchangeRate
from db import db
from datetime import datetime

products_bp = Blueprint('products_bp', __name__)

@products_bp.route('/list_product')
def list_products():
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)

    # --- LÓGICA DE DIVISA ---
    selected_currency = session.get('selected_currency', 'DOP')
    currency_symbol = session.get('currency_symbol', 'RD$')
    raw_rate = ExchangeRate.get_rate(selected_currency, company_id)
    conversion_rate = float(raw_rate) if raw_rate and float(raw_rate) > 0 else 1.0

    # --- FILTROS ---
    category_id = request.args.get('category_id', type=int)
    search_query = request.args.get('search', '').strip()

    categories = Category.query.filter_by(status=True, company_id=company_id).order_by(Category.name.asc()).all()
    query = Product.query.filter_by(status=True, company_id=company_id)

    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search_query:
        query = query.filter(
            (Product.name.ilike(f'%{search_query}%')) |
            (Product.sku.ilike(f'%{search_query}%'))
        )

    products = query.order_by(Product.created_at.desc()).all()

    for p in products:
        p.price = float(p.price)
        p.cost = float(p.cost if p.cost else 0.0)

    return render_template(
        'products/products.html',
        products=products,
        categories=categories,
        selected_category=category_id,
        search_query=search_query,
        user=user,
        currency_symbol=currency_symbol,
        selected_currency=selected_currency,
        conversion_rate=conversion_rate,
        ProductType=ProductType
    )

@products_bp.route('/create_product', methods=['GET', 'POST'])
def create_product():
    company_id = session.get('company_id')
    user_id = session.get('user_id')

    if not company_id or not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    warehouse_id = user.warehouse_id
    categories = Category.query.filter_by(status=True, company_id=company_id).all()

    if request.method == 'POST':
        name = request.form.get('name')
        sku = request.form.get('sku')
        description = request.form.get('description')
        category_id = request.form.get('category_id')
        
        # --- NUEVO: Capturar tipo de producto ---
        type_str = request.form.get('product_type', 'STOCKED')
        product_type = ProductType[type_str]

        # Solo pedimos stock inicial si NO es un servicio
        stock_inicial = int(request.form.get('stock', 0)) if product_type != ProductType.SERVICE else 0

        try:
            selected_currency = session.get('selected_currency', 'DOP')
            rate = float(ExchangeRate.get_rate(selected_currency, company_id) or 1.0)

            input_price = float(request.form.get('price', 0))
            input_cost = float(request.form.get('cost', 0))
            
            base_price = input_price * rate
            base_cost = input_cost * rate
        except (ValueError, TypeError):
            base_price = 0.0
            base_cost = 0.0

        if Product.query.filter_by(sku=sku, company_id=company_id).first():
            flash('El SKU ya existe en su inventario', 'error')
            return redirect(url_for('products_bp.create_product'))

        product = Product(
            name=name,
            sku=sku,
            description=description,
            price=base_price,
            cost=base_cost, 
            category_id=category_id if category_id else None,
            company_id=company_id,
            product_type=product_type, # <--- Guardar el tipo
            status=True
        )

        db.session.add(product)
        db.session.flush()

        # --- Lógica de Stock ---
        # Solo creamos el registro de WarehouseStock si el producto es almacenable
        if product_type != ProductType.SERVICE:
            stock = WarehouseStock(
                product_id=product.id,
                warehouse_id=warehouse_id,
                company_id=company_id,
                quantity=stock_inicial
            )
            db.session.add(stock)
            
        db.session.commit()

        flash(f'Item "{name}" creado correctamente', 'success')
        return redirect(url_for('products_bp.list_products'))

    return render_template('products/create.html', categories=categories, user=user, ProductType=ProductType)

@products_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    user = User.query.get_or_404(user_id)
    product = Product.query.filter_by(id=id, company_id=company_id).first_or_404()
    categories = Category.query.filter_by(status=True, company_id=company_id).all()

    selected_currency = session.get('selected_currency', 'DOP')
    currency_symbol = session.get('currency_symbol', 'RD$')
    rate = float(ExchangeRate.get_rate(selected_currency, company_id) or 1.0)

    if request.method == 'POST':
        product.name = request.form.get('name')
        product.sku = request.form.get('sku')
        product.description = request.form.get('description')
        product.category_id = request.form.get('category_id') or None
        
        # Actualizar tipo de producto
        type_str = request.form.get('product_type')
        if type_str:
            product.product_type = ProductType[type_str]

        try:
            input_price = float(request.form.get('price', 0))
            input_cost = float(request.form.get('cost', 0))
            product.price = input_price * rate
            product.cost = input_cost * rate
        except (ValueError, TypeError):
            pass

        db.session.commit()
        flash('Producto actualizado correctamente', 'success')
        return redirect(url_for('products_bp.list_products'))

    display_price = float(product.price or 0) / rate
    display_cost = float(product.cost or 0) / rate

    return render_template(
        'products/edit.html',
        product=product,
        categories=categories,
        user=user,
        currency_symbol=currency_symbol,
        selected_currency=selected_currency,
        display_price=display_price,
        display_cost=display_cost,
        ProductType=ProductType
    )

@products_bp.route('/delete_product/<int:id>', methods=['POST'])
def delete_product(id):
    company_id = session.get('company_id')
    product = Product.query.filter_by(id=id, company_id=company_id).first_or_404()
    product.status = False
    db.session.commit()
    flash('Producto desactivado', 'info')
    return redirect(url_for('products_bp.list_products'))

@products_bp.route('/product/<int:id>')
def view_product(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get_or_404(user_id)
    product = Product.query.filter_by(id=id, company_id=company_id).first_or_404()

    selected_currency = session.get('selected_currency', 'DOP')
    currency_symbol = session.get('currency_symbol', 'RD$')
    rate = float(ExchangeRate.get_rate(selected_currency, company_id) or 1.0)

    # Si es servicio, los stocks estarán vacíos
    stocks = WarehouseStock.query.filter_by(product_id=id, company_id=company_id).all()

    display_price = float(product.price or 0) / rate
    display_cost = float(product.cost or 0) / rate

    return render_template(
        'products/detail.html',
        product=product,
        user=user,
        stocks=stocks,
        currency_symbol=currency_symbol,
        selected_currency=selected_currency,
        display_price=display_price,
        display_cost=display_cost,
        conversion_rate=rate,
        ProductType=ProductType
    )

@products_bp.route('/api/get-stock')
def get_product_stock_api():
    company_id = session.get('company_id')
    product_id = request.args.get('product_id', type=int)
    warehouse_id = request.args.get('warehouse_id', type=int)

    if not company_id or not product_id or not warehouse_id:
        return jsonify({'error': 'Faltan parámetros'}), 400
    
    # Verificar si el producto es un servicio (los servicios no tienen stock)
    product = Product.query.get(product_id)
    if product and product.product_type == ProductType.SERVICE:
        return jsonify({'product_id': product_id, 'warehouse_id': warehouse_id, 'stock': 0})

    stock_record = WarehouseStock.query.filter_by(
        product_id=product_id,
        warehouse_id=warehouse_id,
        company_id=company_id
    ).first()

    return jsonify({
        'product_id': product_id,
        'warehouse_id': warehouse_id,
        'stock': stock_record.quantity if stock_record else 0
    })

@products_bp.route('/product/<int:id>/stock')
def product_stock_detail(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get_or_404(user_id)
    product = Product.query.filter_by(id=id, company_id=company_id).first_or_404()
    
    # Si es un servicio, podrías redirigir o mostrar un mensaje de que no aplica
    stocks = WarehouseStock.query.filter_by(product_id=id, company_id=company_id).all()

    return render_template(
        'products/stock_detail.html',
        product=product,
        user=user,
        stocks=stocks
    )