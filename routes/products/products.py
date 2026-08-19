from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, current_app
from models.products.products import Product, ProductType 
from models.category.category import Category
from models.user.user import User
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.warehouse_location.warehouse_location import LocationStock, WarehouseLocation
from models.stock_transfer.stock_transfer import StockTransfer
from models.warehouse.warehouse import Warehouse
from models.divisas.divisas import ExchangeRate
from models.company.company import Company
from db import db
from datetime import datetime, timedelta
from io import BytesIO
import logging
from pathlib import Path
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

products_bp = Blueprint('products_bp', __name__)
logger = logging.getLogger(__name__)


def save_product_image(upload, company_id):
    """Verify a raster image, normalize it and store an optimized WebP copy."""
    if not upload or not upload.filename:
        return None

    try:
        image_bytes = upload.read()
        if not image_bytes:
            raise UnidentifiedImageError
        with Image.open(BytesIO(image_bytes)) as source:
            source.verify()
        with Image.open(BytesIO(image_bytes)) as source:
            if getattr(source, 'is_animated', False):
                source.seek(0)
            source = ImageOps.exif_transpose(source).convert('RGBA')
            source.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', source.size, (255, 255, 255, 0))
            canvas.alpha_composite(source)
    except (UnidentifiedImageError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError('La foto no es una imagen válida o está dañada.') from exc
    except OSError as exc:
        raise ValueError('No se pudo leer la foto. Prueba con otra imagen.') from exc

    relative_dir = Path('uploads') / f'company_{company_id}' / 'products'
    absolute_dir = Path(current_app.static_folder) / relative_dir
    filename = f'{uuid4().hex}.webp'
    try:
        absolute_dir.mkdir(parents=True, exist_ok=True)
        canvas.save(absolute_dir / filename, 'WEBP', quality=86, method=6)
        company = db.session.get(Company, company_id)
        company_root = Path(current_app.static_folder) / 'uploads' / f'company_{company_id}'
        usage = sum(path.stat().st_size for path in company_root.rglob('*') if path.is_file())
        if company and usage > int(company.storage_limit or 0):
            (absolute_dir / filename).unlink(missing_ok=True)
            raise ValueError('Tu empresa alcanzó el límite de almacenamiento del plan.')
        if company:
            company.current_storage_usage = usage
    except OSError as exc:
        raise ValueError('No se pudo guardar la foto en el servidor.') from exc
    return (relative_dir / filename).as_posix()


def delete_product_image(relative_path):
    if not relative_path:
        return
    static_root = Path(current_app.static_folder).resolve()
    target = (static_root / relative_path).resolve()
    if static_root in target.parents and target.is_file():
        target.unlink()

@products_bp.route('/list_product')
def list_products():
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = db.session.get(User, user_id)

    # --- LÓGICA DE DIVISA ---
    selected_currency = session.get('selected_currency', 'DOP')
    currency_symbol = session.get('currency_symbol', 'RD$')
    raw_rate = ExchangeRate.get_rate(selected_currency, company_id)
    conversion_rate = float(raw_rate) if raw_rate and float(raw_rate) > 0 else 1.0

    # --- FILTROS ---
    category_id = request.args.get('category_id', type=int)
    search_query = request.args.get('search', '').strip()
    product_type_filter = request.args.get('product_type', '').strip().upper()
    sort_by = request.args.get('sort', 'recent').strip().lower()
    created_from = request.args.get('created_from', '').strip()
    created_to = request.args.get('created_to', '').strip()
    stock_state = request.args.get('stock_state', '').strip().lower()
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)

    categories = Category.query.filter_by(status=True, company_id=company_id).order_by(Category.name.asc()).all()
    query = Product.query.filter_by(status=True, company_id=company_id)

    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search_query:
        query = query.filter(
            (Product.name.ilike(f'%{search_query}%')) |
            (Product.sku.ilike(f'%{search_query}%'))
        )
    if product_type_filter in ProductType.__members__:
        query = query.filter(Product.product_type == ProductType[product_type_filter])
    try:
        if created_from:
            query = query.filter(Product.created_at >= datetime.strptime(created_from, '%Y-%m-%d'))
        if created_to:
            query = query.filter(Product.created_at < datetime.strptime(created_to, '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        flash('El rango de fechas de productos no es válido.', 'warning')
        created_from = created_to = ''
    if min_price is not None:
        query = query.filter(Product.price >= min_price * conversion_rate)
    if max_price is not None:
        query = query.filter(Product.price <= max_price * conversion_rate)

    sort_options = {
        'recent': Product.created_at.desc(),
        'name': Product.name.asc(),
        'price_asc': Product.price.asc(),
        'price_desc': Product.price.desc(),
        'oldest': Product.created_at.asc(),
    }
    if sort_by not in sort_options:
        sort_by = 'recent'
    products = query.order_by(sort_options[sort_by]).all()

    if stock_state == 'available':
        products = [product for product in products if product.product_type == ProductType.SERVICE or product.total_stock > 0]
    elif stock_state == 'low':
        products = [product for product in products if product.product_type != ProductType.SERVICE and 0 < product.total_stock <= 10]
    elif stock_state == 'out':
        products = [product for product in products if product.product_type != ProductType.SERVICE and product.total_stock <= 0]
    elif stock_state:
        stock_state = ''

    for p in products:
        p.price = float(p.price)
        p.cost = float(p.cost if p.cost else 0.0)

    return render_template(
        'products/products.html',
        products=products,
        categories=categories,
        selected_category=category_id,
        search_query=search_query,
        selected_product_type=product_type_filter,
        selected_sort=sort_by,
        created_from=created_from,
        created_to=created_to,
        stock_state=stock_state,
        min_price=min_price,
        max_price=max_price,
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

    user = db.session.get(User, user_id)
    warehouse = None
    if user.warehouse_id:
        warehouse = Warehouse.query.filter_by(id=user.warehouse_id, company_id=company_id, status=True).first()
    if not warehouse:
        warehouse = Warehouse.query.filter_by(company_id=company_id, is_main=True, status=True).first()
    warehouse_id = warehouse.id if warehouse else None
    categories = Category.query.filter_by(status=True, company_id=company_id).all()

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        sku = (request.form.get('sku') or '').strip()
        description = request.form.get('description')
        category_value = (request.form.get('category_id') or '').strip()
        try:
            category_id = int(category_value) if category_value else None
        except ValueError:
            flash('La categoría seleccionada no es válida.', 'danger')
            return redirect(url_for('products_bp.create_product'))
        if category_id:
            category = Category.query.filter_by(id=category_id, company_id=company_id, status=True).first()
            if not category:
                flash('La categoría seleccionada no es válida.', 'danger')
                return redirect(url_for('products_bp.create_product'))
        
        # --- NUEVO: Capturar tipo de producto ---
        type_str = request.form.get('product_type', 'STOCKED')
        if type_str not in ProductType.__members__:
            flash('Tipo de producto inválido.', 'danger')
            return redirect(url_for('products_bp.create_product'))
        product_type = ProductType[type_str]

        # Solo pedimos stock inicial si NO es un servicio
        try:
            stock_inicial = int(request.form.get('stock', 0)) if product_type != ProductType.SERVICE else 0
        except (TypeError, ValueError):
            flash('El inventario inicial debe ser un número entero.', 'danger')
            return redirect(url_for('products_bp.create_product'))

        if not name or not sku:
            flash('Nombre y SKU son obligatorios.', 'danger')
            return redirect(url_for('products_bp.create_product'))
        if product_type != ProductType.SERVICE and not warehouse_id:
            flash('Crea o activa un almacén principal antes de registrar inventario.', 'danger')
            return redirect(url_for('warehouse_bp.list_warehouses'))

        try:
            selected_currency = session.get('selected_currency', 'DOP')
            rate = float(ExchangeRate.get_rate(selected_currency, company_id) or 1.0)

            price_raw = request.form.get('price')
            cost_raw = request.form.get('cost')
            if price_raw in (None, '') or cost_raw in (None, ''):
                raise ValueError
            input_price = float(price_raw)
            input_cost = float(cost_raw)
            if input_price <= 0 or input_cost <= 0:
                raise ValueError
            
            base_price = input_price * rate
            base_cost = input_cost * rate
        except (ValueError, TypeError):
            flash('El costo unitario y el precio de venta son obligatorios y deben ser mayores que cero.', 'danger')
            return redirect(url_for('products_bp.create_product'))

        if Product.query.filter_by(sku=sku, company_id=company_id).first():
            flash('El SKU ya existe en su inventario', 'error')
            return redirect(url_for('products_bp.create_product'))

        try:
            image_path = save_product_image(request.files.get('image'), company_id)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('products_bp.create_product'))

        try:
            min_stock = max(int(request.form.get('min_stock') or 5), 0)
            max_stock = int(request.form['max_stock']) if request.form.get('max_stock') else None
            if max_stock is not None and max_stock < min_stock:
                raise ValueError
        except (TypeError, ValueError):
            if image_path:
                delete_product_image(image_path)
            flash('Los niveles mínimo y máximo de stock no son válidos.', 'danger')
            return redirect(url_for('products_bp.create_product'))

        product = Product(
            name=name,
            sku=sku,
            description=description,
            image_path=image_path,
            price=base_price,
            cost=base_cost, 
            category_id=category_id if category_id else None,
            company_id=company_id,
            product_type=product_type, # <--- Guardar el tipo
            status=True,
            min_stock=min_stock,
            max_stock=max_stock,
        )

        try:
            db.session.add(product)
            db.session.flush()

            # Solo creamos stock si el producto es almacenable.
            if product_type != ProductType.SERVICE:
                stock = WarehouseStock(
                    product_id=product.id,
                    warehouse_id=warehouse_id,
                    company_id=company_id,
                    quantity=stock_inicial
                )
                db.session.add(stock)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            if image_path:
                delete_product_image(image_path)
            logger.exception('No se pudo crear el producto con SKU %s', sku)
            flash('No se pudo guardar el producto. Inténtalo nuevamente.', 'danger')
            return redirect(url_for('products_bp.create_product'))

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
        product.name = (request.form.get('name') or '').strip()
        product.sku = (request.form.get('sku') or '').strip()
        if not product.name or not product.sku:
            flash('Nombre y SKU son obligatorios.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        duplicate = Product.query.filter(
            Product.company_id == company_id,
            Product.sku == product.sku,
            Product.id != product.id
        ).first()
        if duplicate:
            flash('El SKU ya existe en su inventario.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        product.description = request.form.get('description')
        category_value = (request.form.get('category_id') or '').strip()
        try:
            category_id = int(category_value) if category_value else None
        except ValueError:
            flash('La categoría seleccionada no es válida.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        if category_id and not Category.query.filter_by(id=category_id, company_id=company_id, status=True).first():
            flash('La categoría seleccionada no es válida.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        product.category_id = category_id
        try:
            product.min_stock = max(int(request.form.get('min_stock') or 0), 0)
            product.max_stock = int(request.form['max_stock']) if request.form.get('max_stock') else None
            if product.max_stock is not None and product.max_stock < product.min_stock:
                raise ValueError
        except (TypeError, ValueError):
            flash('Los niveles mínimo y máximo de stock no son válidos.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        
        # Actualizar tipo de producto
        type_str = request.form.get('product_type')
        if type_str:
            if type_str not in ProductType.__members__:
                flash('Tipo de producto inválido.', 'danger')
                return redirect(url_for('products_bp.edit_product', id=id))
            product.product_type = ProductType[type_str]

        try:
            price_raw = request.form.get('price')
            cost_raw = request.form.get('cost')
            if price_raw in (None, '') or cost_raw in (None, ''):
                raise ValueError
            input_price = float(price_raw)
            input_cost = float(cost_raw)
            if input_price <= 0 or input_cost <= 0:
                raise ValueError
            product.price = input_price * rate
            product.cost = input_cost * rate
        except (ValueError, TypeError):
            flash('El costo unitario y el precio de venta son obligatorios y deben ser mayores que cero.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))

        old_image = product.image_path
        try:
            new_image = save_product_image(request.files.get('image'), company_id)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        if new_image:
            product.image_path = new_image
        elif request.form.get('remove_image') == '1':
            product.image_path = None

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            if new_image:
                delete_product_image(new_image)
            logger.exception('No se pudo actualizar el producto %s', product.id)
            flash('No se pudo guardar el producto. Inténtalo nuevamente.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        if old_image and old_image != product.image_path:
            delete_product_image(old_image)
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
    location_id = request.args.get('location_id', type=int)

    if not company_id or not product_id or not warehouse_id:
        return jsonify({'error': 'Faltan parámetros'}), 400
    
    # Verificar si el producto es un servicio (los servicios no tienen stock)
    product = Product.query.filter_by(id=product_id, company_id=company_id).first()
    warehouse = Warehouse.query.filter_by(id=warehouse_id, company_id=company_id, status=True).first()
    if not product or not warehouse:
        return jsonify({'error': 'Producto o almacén no encontrado'}), 404
    if product and product.product_type == ProductType.SERVICE:
        return jsonify({'product_id': product_id, 'warehouse_id': warehouse_id, 'stock': 0})

    if location_id:
        location = WarehouseLocation.query.filter_by(
            id=location_id,
            warehouse_id=warehouse_id,
            company_id=company_id,
            status=True,
        ).first()
        if not location:
            return jsonify({'error': 'Ubicación no válida'}), 404
        stock_record = LocationStock.query.filter_by(
            product_id=product_id,
            location_id=location_id,
            company_id=company_id,
        ).first()
        reserved = db.session.query(func.coalesce(func.sum(StockTransfer.quantity), 0)).filter(
            StockTransfer.company_id == company_id,
            StockTransfer.product_id == product_id,
            StockTransfer.from_location_id == location_id,
            StockTransfer.status == 'PENDING',
        ).scalar()
        return jsonify({
            'product_id': product_id,
            'warehouse_id': warehouse_id,
            'location_id': location_id,
            'location': location.full_path,
            'stock': max(int(stock_record.quantity or 0) - int(reserved or 0), 0) if stock_record else 0,
        })

    stock_record = WarehouseStock.query.filter_by(
        product_id=product_id,
        warehouse_id=warehouse_id,
        company_id=company_id
    ).first()

    allocated = db.session.query(func.coalesce(func.sum(LocationStock.quantity), 0)).join(
        WarehouseLocation, LocationStock.location_id == WarehouseLocation.id
    ).filter(
        WarehouseLocation.warehouse_id == warehouse_id,
        LocationStock.product_id == product_id,
        LocationStock.company_id == company_id,
    ).scalar()
    reserved = db.session.query(func.coalesce(func.sum(StockTransfer.quantity), 0)).filter(
        StockTransfer.company_id == company_id,
        StockTransfer.product_id == product_id,
        StockTransfer.from_warehouse_id == warehouse_id,
        StockTransfer.from_location_id.is_(None),
        StockTransfer.status == 'PENDING',
    ).scalar()

    return jsonify({
        'product_id': product_id,
        'warehouse_id': warehouse_id,
        'stock': max(int(stock_record.quantity or 0) - int(allocated or 0) - int(reserved or 0), 0) if stock_record else 0
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
