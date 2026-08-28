from services.time_utils import utcnow
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, current_app
from models.products.products import Product, ProductType 
from models.category.category import Category
from models.user.user import User
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.warehouse_location.warehouse_location import LocationStock, WarehouseLocation
from models.stock_transfer.stock_transfer import StockTransfer
from models.stock_movement.stock_movement import StockMovement
from models.warehouse.warehouse import Warehouse
from models.divisas.divisas import ExchangeRate
from models.company.company import Company
from db import db
from datetime import datetime, timedelta
from io import BytesIO
from decimal import Decimal
import logging
from pathlib import Path
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from services.numeric import bounded_decimal, finite_decimal
from services.validation import BusinessRuleError, positive_money
from services.quantity import non_negative_quantity, as_decimal
from services.retail import get_retail_settings
from services.product_images import product_image_url
from models.retail import (UnitOfMeasure, ProductUomConversion, ProductAttribute, ProductVariant, ProductBarcode, WarehouseVariantStock,
                           PriceList, PriceListRule, ProductSupplier, ProductBundleItem, InventoryLot, InventorySerial,
                           WarrantyClaim, InventoryConditionStock)
from models.supplier.supplier import Supplier
from models.sales.sale_item import SaleItem

products_bp = Blueprint('products_bp', __name__)
logger = logging.getLogger(__name__)


def _product_exchange_rate(selected_currency, company_id, *, strict=False):
    """Resolve a finite positive rate; writes fail closed, displays fall back safely."""
    try:
        rate = finite_decimal(
            ExchangeRate.get_rate(selected_currency, company_id),
            field_name='Tasa de conversión',
        )
        if rate <= 0:
            raise BusinessRuleError('La tasa de conversión debe ser mayor que cero.')
        return rate
    except (BusinessRuleError, RuntimeError, TypeError, ValueError) as exc:
        if strict and selected_currency != 'DOP':
            raise BusinessRuleError(
                f'No hay una tasa válida para {selected_currency}. Configúrala antes de guardar importes.'
            ) from exc
        logger.warning(
            'Usando tasa 1 solo para visualización; company_id=%s currency=%s: %s',
            company_id, selected_currency, exc,
        )
        return Decimal('1')


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


def _validate_product_uoms(company_id, base_uom_id, sale_uom_id, purchase_uom_id):
    ids = {value for value in (base_uom_id, sale_uom_id, purchase_uom_id) if value}
    if not ids:
        return None, None, None
    rows = UnitOfMeasure.query.filter(
        UnitOfMeasure.company_id == company_id, UnitOfMeasure.active.is_(True), UnitOfMeasure.id.in_(ids)
    ).all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(ids):
        raise BusinessRuleError('Una de las unidades de medida no pertenece a esta empresa o está inactiva.')
    base = by_id.get(base_uom_id) if base_uom_id else None
    if not base:
        raise BusinessRuleError('Selecciona una unidad base antes de definir unidades de venta o compra.')
    for value, label in ((sale_uom_id, 'venta'), (purchase_uom_id, 'compra')):
        unit = by_id.get(value) if value else None
        if unit and unit.category != base.category:
            raise BusinessRuleError(f'La unidad de {label} debe pertenecer a la misma categoría que la unidad base.')
    return base.id, sale_uom_id or base.id, purchase_uom_id or base.id


def _ensure_default_uom_factor(company_id, product_id, base_uom_id, sale_uom_id, purchase_uom_id):
    """Reject ambiguous packaging defaults such as Caja=x1 without an explicit product factor."""
    if not base_uom_id:
        return
    ids = {value for value in (base_uom_id, sale_uom_id, purchase_uom_id) if value}
    units = UnitOfMeasure.query.filter(
        UnitOfMeasure.company_id == company_id,
        UnitOfMeasure.active.is_(True),
        UnitOfMeasure.id.in_(ids),
    ).all()
    by_id = {row.id: row for row in units}
    base = by_id.get(base_uom_id)
    if not base:
        return
    explicit = set()
    if product_id:
        explicit = {
            row.uom_id for row in ProductUomConversion.query.filter_by(
                company_id=company_id, product_id=product_id
            ).all()
        }
    base_factor = Decimal(str(base.factor_to_reference or 1))
    for uom_id, label in ((sale_uom_id, 'venta'), (purchase_uom_id, 'compra')):
        if not uom_id or uom_id == base_uom_id or uom_id in explicit:
            continue
        unit = by_id.get(uom_id)
        if not unit:
            continue
        unit_factor = Decimal(str(unit.factor_to_reference or 1))
        # A non-base UOM with a different company-wide factor is a physical
        # conversion (kg/g, m/cm, etc.). Equal factors are ambiguous packaging
        # (Caja/Paquete) and must be defined per product.
        if unit_factor == base_factor:
            raise BusinessRuleError(
                f'Define primero la conversión de {unit.name} para este producto antes de usarla como unidad de {label}. '
                'Crea el producto con su unidad base y configura la equivalencia en la ficha (por ejemplo, 1 caja = 24 unidades).'
            )


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

    selected_currency = session.get('selected_currency', 'DOP')
    currency_symbol = session.get('currency_symbol', 'RD$')
    conversion_rate = _product_exchange_rate(selected_currency, company_id)

    scope = (request.args.get('scope') or 'active').strip().lower()
    if scope not in {'active', 'archived'}:
        scope = 'active'

    category_id = request.args.get('category_id', type=int)
    search_query = request.args.get('search', '').strip()
    product_type_filter = request.args.get('product_type', '').strip().upper()
    sort_by = request.args.get('sort', 'recent').strip().lower()
    created_from = request.args.get('created_from', '').strip()
    created_to = request.args.get('created_to', '').strip()
    stock_state = request.args.get('stock_state', '').strip().lower()
    min_price_raw = (request.args.get('min_price') or '').strip()
    max_price_raw = (request.args.get('max_price') or '').strip()
    min_price = max_price = None
    try:
        if min_price_raw:
            min_price = bounded_decimal(
                min_price_raw, field_name='Precio mínimo', places=2,
                minimum='0', maximum='99999999.99',
            )
        if max_price_raw:
            max_price = bounded_decimal(
                max_price_raw, field_name='Precio máximo', places=2,
                minimum='0', maximum='99999999.99',
            )
        if min_price is not None and max_price is not None and min_price > max_price:
            raise BusinessRuleError('El precio mínimo no puede superar el precio máximo.')
    except BusinessRuleError as exc:
        flash(str(exc), 'warning')
        min_price = max_price = None

    categories = Category.query.filter_by(status=True, company_id=company_id).order_by(Category.name.asc()).all()
    active_count = Product.query.filter(
        Product.company_id == company_id,
        Product.archived_at.is_(None),
        Product.status.is_(True),
    ).count()
    archived_count = Product.query.filter(
        Product.company_id == company_id,
        Product.archived_at.isnot(None),
    ).count()

    query = Product.query.filter(Product.company_id == company_id)
    if scope == 'archived':
        query = query.filter(Product.archived_at.isnot(None))
    else:
        query = query.filter(Product.archived_at.is_(None), Product.status.is_(True))

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
        'recent': Product.archived_at.desc() if scope == 'archived' else Product.created_at.desc(),
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

    image_urls = {product.id: product_image_url(product) for product in products}

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
        scope=scope,
        active_count=active_count,
        archived_count=archived_count,
        user=user,
        currency_symbol=currency_symbol,
        selected_currency=selected_currency,
        conversion_rate=conversion_rate,
        ProductType=ProductType,
        image_urls=image_urls,
    )

@products_bp.route('/create_product', methods=['GET', 'POST'])
def create_product():
    company_id = session.get('company_id')
    user_id = session.get('user_id')

    if not company_id or not user_id:
        return redirect(url_for('login_bp.login'))

    user = db.session.get(User, user_id)
    warehouses = Warehouse.query.filter_by(company_id=company_id, status=True).order_by(Warehouse.is_main.desc(), Warehouse.name.asc()).all()
    warehouse = None
    if user.warehouse_id:
        warehouse = next((row for row in warehouses if row.id == user.warehouse_id), None)
    if not warehouse:
        warehouse = next((row for row in warehouses if row.is_main), None) or (warehouses[0] if warehouses else None)
    warehouse_id = warehouse.id if warehouse else None
    categories = Category.query.filter_by(status=True, company_id=company_id).all()
    uoms = UnitOfMeasure.query.filter_by(company_id=company_id, active=True).order_by(UnitOfMeasure.category.asc(), UnitOfMeasure.name.asc()).all()
    retail_settings = get_retail_settings(company_id, create=True)

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

        sale_mode = 'WEIGHT' if request.form.get('sale_mode') == 'WEIGHT' else 'UNIT'
        tracking = (request.form.get('tracking') or 'NONE').upper()
        if tracking not in {'NONE', 'LOT', 'SERIAL'}:
            tracking = 'NONE'
        requested_base_uom_id = request.form.get('base_uom_id', type=int)
        base_uom_for_precision = UnitOfMeasure.query.filter_by(
            id=requested_base_uom_id, company_id=company_id, active=True
        ).first() if requested_base_uom_id else None
        if tracking == 'SERIAL' and (
            sale_mode == 'WEIGHT' or bool(base_uom_for_precision and base_uom_for_precision.allow_fraction)
        ):
            flash('Los productos serializados deben venderse y controlarse por unidades enteras.', 'danger')
            return redirect(url_for('products_bp.create_product'))
        fractional_quantity = tracking != 'SERIAL' and (
            sale_mode == 'WEIGHT' or bool(base_uom_for_precision and base_uom_for_precision.allow_fraction)
        )

        selected_warehouse_id = request.form.get('warehouse_id', type=int) or warehouse_id
        selected_warehouse = Warehouse.query.filter_by(
            id=selected_warehouse_id, company_id=company_id, status=True
        ).first() if selected_warehouse_id else None

        # El inventario inicial respeta la precisión real del producto. Las unidades
        # discretas usan enteros; peso/medidas admiten hasta tres decimales.
        try:
            stock_inicial = non_negative_quantity(
                request.form.get('stock', 0), 'Inventario inicial', fractional=fractional_quantity
            ) if product_type != ProductType.SERVICE else Decimal('0')
        except BusinessRuleError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('products_bp.create_product'))

        if not name or not sku:
            flash('Nombre y SKU son obligatorios.', 'danger')
            return redirect(url_for('products_bp.create_product'))
        if len(name) > 150 or len(sku) > 50:
            flash('El nombre admite hasta 150 caracteres y el SKU hasta 50.', 'danger')
            return redirect(url_for('products_bp.create_product'))
        if product_type != ProductType.SERVICE and not selected_warehouse:
            flash('Selecciona un almacén activo para registrar el inventario inicial.', 'danger')
            return redirect(url_for('products_bp.create_product'))

        try:
            selected_currency = session.get('selected_currency', 'DOP')
            rate = _product_exchange_rate(selected_currency, company_id, strict=True)

            price_raw = request.form.get('price')
            cost_raw = request.form.get('cost')
            if price_raw in (None, '') or cost_raw in (None, ''):
                raise ValueError
            input_price = positive_money(price_raw, 'Precio de venta')
            input_cost = positive_money(cost_raw, 'Costo unitario')
            
            base_price = input_price * rate
            base_cost = input_cost * rate
        except BusinessRuleError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('products_bp.create_product'))
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

        if product_type != ProductType.SERVICE and stock_inicial > 0 and tracking in {'LOT', 'SERIAL'}:
            if image_path:
                delete_product_image(image_path)
            flash('Para productos por lote o serial, crea el producto con inventario inicial en 0 y registra la trazabilidad desde su ficha.', 'danger')
            return redirect(url_for('products_bp.create_product'))

        try:
            min_stock = non_negative_quantity(request.form.get('min_stock') or 5, 'Stock mínimo', fractional=fractional_quantity)
            max_stock = non_negative_quantity(request.form['max_stock'], 'Stock máximo', fractional=fractional_quantity) if request.form.get('max_stock') else None
            if max_stock is not None and max_stock < min_stock:
                raise ValueError
        except (TypeError, ValueError, BusinessRuleError):
            if image_path:
                delete_product_image(image_path)
            flash('Los niveles mínimo y máximo de stock no son válidos.', 'danger')
            return redirect(url_for('products_bp.create_product'))

        try:
            base_uom_id, sale_uom_id, purchase_uom_id = _validate_product_uoms(
                company_id, requested_base_uom_id,
                request.form.get('sale_uom_id', type=int), request.form.get('purchase_uom_id', type=int),
            )
            _ensure_default_uom_factor(company_id, None, base_uom_id, sale_uom_id, purchase_uom_id)
        except BusinessRuleError as exc:
            if image_path:
                delete_product_image(image_path)
            flash(str(exc), 'danger')
            return redirect(url_for('products_bp.create_product'))

        try:
            warranty_days = int(request.form.get('warranty_days') or 30)
        except (TypeError, ValueError):
            warranty_days = 0
        if warranty_days < 1 or warranty_days > 3650:
            if image_path:
                delete_product_image(image_path)
            flash('Selecciona un plazo de garantía entre 1 día y 10 años.', 'danger')
            return redirect(url_for('products_bp.create_product'))

        product = Product(
            name=name,
            sku=sku,
            description=description,
            image_path=image_path,
            image_url=None,
            price=base_price,
            cost=base_cost, 
            category_id=category_id if category_id else None,
            company_id=company_id,
            product_type=product_type, # <--- Guardar el tipo
            status=True,
            min_stock=min_stock,
            max_stock=max_stock,
            brand=(request.form.get('brand') or '').strip() or None,
            sale_mode=sale_mode,
            tracking=tracking,
            warranty_days=warranty_days,
            base_uom_id=base_uom_id,
            sale_uom_id=sale_uom_id,
            purchase_uom_id=purchase_uom_id,
        )

        try:
            db.session.add(product)
            db.session.flush()

            # Solo creamos stock si el producto es almacenable.
            if product_type != ProductType.SERVICE:
                stock = WarehouseStock(
                    product_id=product.id,
                    warehouse_id=selected_warehouse.id,
                    company_id=company_id,
                    quantity=stock_inicial
                )
                db.session.add(stock)
                if stock_inicial > 0:
                    db.session.add(StockMovement(
                        company_id=company_id, user_id=session.get('user_id'),
                        product_id=product.id,
                        warehouse_id=selected_warehouse.id,
                        movement_type='IN',
                        quantity=stock_inicial,
                        reason='Inventario inicial del producto',
                    ))
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

    return render_template('products/create.html', categories=categories, user=user, ProductType=ProductType, uoms=uoms, retail_settings=retail_settings, warehouses=warehouses, default_warehouse_id=warehouse_id)

@products_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    user = User.query.get_or_404(user_id)
    product = Product.query.filter_by(id=id, company_id=company_id).filter(Product.archived_at.is_(None)).first_or_404()
    categories = Category.query.filter_by(status=True, company_id=company_id).all()
    uoms = UnitOfMeasure.query.filter_by(company_id=company_id, active=True).order_by(UnitOfMeasure.category.asc(), UnitOfMeasure.name.asc()).all()
    uom_conversions = ProductUomConversion.query.filter_by(company_id=company_id, product_id=product.id).order_by(ProductUomConversion.factor_to_base.asc()).all()
    retail_settings = get_retail_settings(company_id, create=True)

    selected_currency = session.get('selected_currency', 'DOP')
    currency_symbol = session.get('currency_symbol', 'RD$')
    try:
        rate = _product_exchange_rate(
            selected_currency, company_id, strict=request.method == 'POST'
        )
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('products_bp.edit_product', id=id))

    if request.method == 'POST':
        product.name = (request.form.get('name') or '').strip()
        product.sku = (request.form.get('sku') or '').strip()
        if not product.name or not product.sku:
            flash('Nombre y SKU son obligatorios.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        if len(product.name) > 150 or len(product.sku) > 50:
            flash('El nombre admite hasta 150 caracteres y el SKU hasta 50.', 'danger')
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
        requested_base_uom_id = request.form.get('base_uom_id', type=int)
        base_uom_for_precision = UnitOfMeasure.query.filter_by(
            id=requested_base_uom_id, company_id=company_id, active=True
        ).first() if requested_base_uom_id else None
        sale_mode = 'WEIGHT' if request.form.get('sale_mode') == 'WEIGHT' else 'UNIT'
        tracking = (request.form.get('tracking') or 'NONE').upper()
        if tracking not in {'NONE', 'LOT', 'SERIAL'}:
            tracking = 'NONE'
        if tracking == 'SERIAL' and (
            sale_mode == 'WEIGHT' or bool(base_uom_for_precision and base_uom_for_precision.allow_fraction)
        ):
            flash('Los productos serializados deben venderse y controlarse por unidades enteras.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        fractional_stock = tracking != 'SERIAL' and (
            sale_mode == 'WEIGHT' or bool(base_uom_for_precision and base_uom_for_precision.allow_fraction)
        )
        try:
            product.min_stock = non_negative_quantity(request.form.get('min_stock') or 0, 'Stock mínimo', fractional=fractional_stock)
            product.max_stock = non_negative_quantity(request.form['max_stock'], 'Stock máximo', fractional=fractional_stock) if request.form.get('max_stock') else None
            if product.max_stock is not None and product.max_stock < product.min_stock:
                raise ValueError
        except (TypeError, ValueError, BusinessRuleError):
            flash('Los niveles mínimo y máximo de stock no son válidos.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        
        # Actualizar tipo de producto
        type_str = request.form.get('product_type')
        if type_str:
            if type_str not in ProductType.__members__:
                flash('Tipo de producto inválido.', 'danger')
                return redirect(url_for('products_bp.edit_product', id=id))
            product.product_type = ProductType[type_str]

        product.brand = (request.form.get('brand') or '').strip() or None
        product.sale_mode = sale_mode
        product.tracking = tracking
        try:
            product.warranty_days = int(request.form.get('warranty_days') or 30)
        except (TypeError, ValueError):
            product.warranty_days = 0
        if product.warranty_days < 1 or product.warranty_days > 3650:
            flash('Selecciona un plazo de garantía entre 1 día y 10 años.', 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        try:
            base_uom_id, sale_uom_id, purchase_uom_id = _validate_product_uoms(
                company_id, requested_base_uom_id,
                request.form.get('sale_uom_id', type=int), request.form.get('purchase_uom_id', type=int),
            )
            _ensure_default_uom_factor(company_id, product.id, base_uom_id, sale_uom_id, purchase_uom_id)
        except BusinessRuleError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('products_bp.edit_product', id=id))
        product.base_uom_id = base_uom_id
        product.sale_uom_id = sale_uom_id
        product.purchase_uom_id = purchase_uom_id

        try:
            price_raw = request.form.get('price')
            cost_raw = request.form.get('cost')
            if price_raw in (None, '') or cost_raw in (None, ''):
                raise ValueError
            input_price = positive_money(price_raw, 'Precio de venta')
            input_cost = positive_money(cost_raw, 'Costo unitario')
            product.price = input_price * rate
            product.cost = input_cost * rate
        except (BusinessRuleError, ValueError, TypeError):
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
            product.image_url = None
        elif request.form.get('remove_image') == '1':
            product.image_path = None
            product.image_url = None

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

    display_price = Decimal(product.price or 0) / rate
    display_cost = Decimal(product.cost or 0) / rate

    return render_template(
        'products/edit.html',
        product=product,
        categories=categories,
        user=user,
        currency_symbol=currency_symbol,
        selected_currency=selected_currency,
        display_price=display_price,
        display_cost=display_cost,
        ProductType=ProductType, uoms=uoms, retail_settings=retail_settings
    )

@products_bp.route('/delete_product/<int:id>', methods=['POST'])
def delete_product(id):
    company_id = session.get('company_id')
    product = Product.query.filter_by(id=id, company_id=company_id).filter(Product.archived_at.is_(None)).first_or_404()
    product.status = False
    product.archived_at = utcnow()
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception('No se pudo archivar el producto %s', id)
        flash('No se pudo archivar el producto. Inténtalo nuevamente.', 'danger')
        return redirect(url_for('products_bp.list_products'))
    flash(f'Producto "{product.name}" archivado.', 'info')
    return redirect(url_for('products_bp.list_products'))


@products_bp.route('/restore_product/<int:id>', methods=['POST'])
def restore_product(id):
    company_id = session.get('company_id')
    product = Product.query.filter_by(id=id, company_id=company_id).filter(Product.archived_at.isnot(None)).first_or_404()
    product.archived_at = None
    product.status = True
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception('No se pudo restaurar el producto %s', id)
        flash('No se pudo restaurar el producto. Inténtalo nuevamente.', 'danger')
        return redirect(url_for('products_bp.list_products', scope='archived'))
    flash(f'Producto "{product.name}" restaurado al catálogo.', 'success')
    return redirect(url_for('products_bp.list_products', scope='archived'))

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
    rate = _product_exchange_rate(selected_currency, company_id)

    # Si es servicio, los stocks estarán vacíos
    stocks = WarehouseStock.query.filter_by(product_id=id, company_id=company_id).all()

    display_price = Decimal(product.price or 0) / rate
    display_cost = Decimal(product.cost or 0) / rate

    retail_settings = get_retail_settings(company_id, create=True)
    uoms = UnitOfMeasure.query.filter_by(company_id=company_id, active=True).order_by(UnitOfMeasure.category.asc(), UnitOfMeasure.name.asc()).all()
    uom_conversions = ProductUomConversion.query.filter_by(company_id=company_id, product_id=product.id).order_by(ProductUomConversion.factor_to_base.asc()).all()
    attributes = ProductAttribute.query.filter_by(company_id=company_id, active=True).order_by(ProductAttribute.sequence.asc(), ProductAttribute.name.asc()).all()
    variants = ProductVariant.query.filter_by(company_id=company_id, product_id=product.id, active=True).order_by(ProductVariant.name.asc()).all()
    barcodes = ProductBarcode.query.filter_by(company_id=company_id, product_id=product.id).order_by(ProductBarcode.is_primary.desc(), ProductBarcode.code.asc()).all()
    variant_stocks = WarehouseVariantStock.query.filter_by(company_id=company_id, product_id=product.id).all()
    variant_stock_map = {(row.variant_id, row.warehouse_id): row.quantity for row in variant_stocks}
    price_rules = PriceListRule.query.filter_by(company_id=company_id, product_id=product.id, active=True).all()
    supplier_links = ProductSupplier.query.filter_by(company_id=company_id, product_id=product.id).order_by(ProductSupplier.preferred.desc(), ProductSupplier.unit_cost.asc()).all()
    suppliers = Supplier.query.filter_by(company_id=company_id, archived_at=None).order_by(Supplier.name.asc()).all()
    bundle_items = ProductBundleItem.query.filter_by(company_id=company_id, bundle_product_id=product.id).all()
    component_products = Product.query.filter(Product.company_id == company_id, Product.id != product.id, Product.status.is_(True), Product.archived_at.is_(None)).order_by(Product.name.asc()).all()
    lots = InventoryLot.query.filter_by(company_id=company_id, product_id=product.id).order_by(InventoryLot.expires_at.asc().nullslast(), InventoryLot.received_at.desc()).limit(100).all()
    serials = InventorySerial.query.filter_by(company_id=company_id, product_id=product.id).order_by(InventorySerial.acquired_at.desc()).limit(100).all()
    warranty_claims = WarrantyClaim.query.join(SaleItem, WarrantyClaim.sale_item_id == SaleItem.id).filter(WarrantyClaim.company_id == company_id, SaleItem.product_id == product.id).order_by(WarrantyClaim.opened_at.desc()).limit(50).all()
    condition_stocks = InventoryConditionStock.query.filter_by(company_id=company_id, product_id=product.id).order_by(InventoryConditionStock.condition.asc()).all()

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
        ProductType=ProductType, retail_settings=retail_settings, uoms=uoms, uom_conversions=uom_conversions, attributes=attributes, variants=variants,
        barcodes=barcodes, variant_stock_map=variant_stock_map, price_rules=price_rules, supplier_links=supplier_links,
        suppliers=suppliers, bundle_items=bundle_items, component_products=component_products, lots=lots, serials=serials,
        warranty_claims=warranty_claims, condition_stocks=condition_stocks
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
    product = Product.query.filter_by(id=product_id, company_id=company_id).filter(Product.archived_at.is_(None)).first()
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
            'stock': float(max(as_decimal(stock_record.quantity) - as_decimal(reserved or 0), as_decimal(0))) if stock_record else 0,
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
        'stock': float(max(as_decimal(stock_record.quantity) - as_decimal(allocated or 0) - as_decimal(reserved or 0), as_decimal(0))) if stock_record else 0
    })

@products_bp.route('/product/<int:id>/stock')
def product_stock_detail(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get_or_404(user_id)
    product = Product.query.filter_by(id=id, company_id=company_id).filter(Product.archived_at.is_(None)).first_or_404()
    
    # Si es un servicio, podrías redirigir o mostrar un mensaje de que no aplica
    stocks = WarehouseStock.query.filter_by(product_id=id, company_id=company_id).all()

    return render_template(
        'products/stock_detail.html',
        product=product,
        user=user,
        stocks=stocks
    )
