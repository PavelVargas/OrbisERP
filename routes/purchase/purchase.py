from services.numeric import NumericValueError, finite_decimal
from flask import Blueprint, render_template, redirect, url_for, request, abort, flash, session, current_app, g
from models.purchase.purchase_order import PurchaseOrder
from models.purchase.purchase_order_item import PurchaseOrderItem
from models.purchase.purchase_tax import PurchaseTax
from models.backoffice import SupplierBill
from models.stock_movement.stock_movement import StockMovement
from models.products.products import Product
from models.supplier.supplier import Supplier
from models.user.user import User
from db import db
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from decimal import ROUND_HALF_UP
from services.quantity import as_decimal, base_quantity_from_factor, product_quantity
from services.retail import uom_to_base
from services.costing import register_receipt_cost
from services.validation import BusinessRuleError
from models.retail import ProductVariant, UnitOfMeasure, ProductUomConversion, WarehouseVariantStock, InventoryLot, InventorySerial
from datetime import datetime, timedelta
from sqlalchemy import String, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

purchase_bp = Blueprint('purchase_bp', __name__)

def _positive_money(raw_value, field_name):
    value = finite_decimal(raw_value, field_name=field_name)
    if value <= 0:
        raise BusinessRuleError(f'{field_name} debe ser mayor que cero.')
    quantized = value.quantize(finite_decimal('0.01'), rounding=ROUND_HALF_UP)
    if quantized != value:
        raise BusinessRuleError(f'{field_name} admite como máximo 2 decimales.')
    if quantized > finite_decimal('99999999.99'):
        raise BusinessRuleError(f'{field_name} supera el máximo permitido.')
    return quantized


def _tax_rate(raw_value):
    value = finite_decimal(raw_value, field_name='Porcentaje de ITBIS')
    quantized = value.quantize(finite_decimal('0.01'), rounding=ROUND_HALF_UP)
    if quantized != value or quantized < 0 or quantized > 100:
        raise BusinessRuleError(
            'El porcentaje debe estar entre 0 y 100 y admitir como máximo 2 decimales.'
        )
    return quantized


def _refresh_order_totals(order):
    db.session.flush()
    items = PurchaseOrderItem.query.filter_by(purchase_order_id=order.id).all()
    order.total_items = sum((as_decimal(item.quantity) for item in items), finite_decimal('0'))
    order.subtotal = sum((item.net_subtotal for item in items), finite_decimal('0.00')).quantize(finite_decimal('0.01'))
    order.tax_total = sum((item.tax_amount for item in items), finite_decimal('0.00')).quantize(finite_decimal('0.01'))
    order.total_cost = sum((item.line_total for item in items), finite_decimal('0.00')).quantize(finite_decimal('0.01'))


def _purchase_taxes(company_id):
    """Create safe defaults once and return the company's active purchase taxes."""
    taxes = PurchaseTax.query.filter_by(company_id=company_id, active=True).order_by(
        PurchaseTax.rate.asc(), PurchaseTax.price_included.asc(), PurchaseTax.name.asc()
    ).all()
    defaults = (
        ('ITBIS exento', finite_decimal('0.00'), False),
        ('ITBIS 18% no incluido', finite_decimal('18.00'), False),
        ('ITBIS 18% incluido', finite_decimal('18.00'), True),
    )
    known_names = {tax.name.lower() for tax in taxes}
    missing = [PurchaseTax(name=name, rate=rate, price_included=included, company_id=company_id)
               for name, rate, included in defaults if name.lower() not in known_names]
    if missing:
        db.session.add_all(missing)
        db.session.commit()
    return PurchaseTax.query.filter_by(company_id=company_id, active=True).order_by(
        PurchaseTax.rate.asc(), PurchaseTax.price_included.asc(), PurchaseTax.name.asc()
    ).all()

# =========================
# LISTA DE ÓRDENES
# =========================
@purchase_bp.route('/purchase')
def purchase_list():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = db.session.get(User, user_id)
    query = PurchaseOrder.query.options(
        joinedload(PurchaseOrder.supplier),
        selectinload(PurchaseOrder.items),
    ).filter_by(company_id=company_id)

    search = (request.args.get('q') or '').strip()
    status = (request.args.get('status') or '').strip().upper()
    supplier_id = request.args.get('supplier_id', type=int)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    if search:
        like = f'%{search}%'
        query = query.filter(or_(
            PurchaseOrder.supplier_name.ilike(like),
            cast(PurchaseOrder.id, String).ilike(like),
        ))
    if status in {'PENDING', 'RECEIVED', 'CANCELLED'}:
        query = query.filter(PurchaseOrder.status == status)
    else:
        status = ''
    if supplier_id:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)
    try:
        if date_from:
            query = query.filter(PurchaseOrder.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        if date_to:
            query = query.filter(PurchaseOrder.created_at < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        flash('El rango de fechas no es válido.', 'warning')

    orders = query.order_by(PurchaseOrder.created_at.desc()).limit(1000).all()
    all_orders = PurchaseOrder.query.filter_by(company_id=company_id).all()
    stats = {
        'total': len(all_orders),
        'pending': sum(1 for order in all_orders if order.status == 'PENDING'),
        'received': sum(1 for order in all_orders if order.status == 'RECEIVED'),
        'invested': sum((finite_decimal(order.total_cost or 0) for order in all_orders if order.status == 'RECEIVED'), finite_decimal('0.00')),
    }
    suppliers = Supplier.query.filter_by(company_id=company_id).filter(Supplier.archived_at.is_(None)).order_by(Supplier.name.asc()).all()
    filters_active = bool(search or status or supplier_id or date_from or date_to)

    return render_template(
        'purchase/purchase_list.html', orders=orders, user=user, stats=stats,
        suppliers=suppliers, filters_active=filters_active,
        filters={'q': search, 'status': status, 'supplier_id': supplier_id,
                 'date_from': date_from, 'date_to': date_to},
    )

# =========================
# CREAR ORDEN (Paso 1: Seleccionar Proveedor)
# =========================
@purchase_bp.route('/purchase/create', methods=['GET', 'POST'])
def create_purchase():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    suppliers = Supplier.query.filter_by(company_id=company_id).filter(Supplier.archived_at.is_(None)).order_by(Supplier.name.asc()).all()
    
    if request.method == 'POST':
        # Conversión a int() para evitar error de PostgreSQL
        supplier_id = request.form.get('supplier_id', type=int)
        if not supplier_id:
            flash('No se creó la orden: selecciona un proveedor válido antes de continuar. Si acabas de crear uno, verifica que haya quedado seleccionado.', 'warning')
            return render_template('purchase/create_purchase.html', suppliers=suppliers, user=user), 400
        supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).filter(Supplier.archived_at.is_(None)).first()
        if not supplier:
            flash('No se creó la orden: el proveedor seleccionado no existe, está archivado o pertenece a otra empresa.', 'danger')
            return render_template('purchase/create_purchase.html', suppliers=suppliers, user=user), 400
        
        order = PurchaseOrder(
            supplier_id=supplier.id, 
            supplier_name=supplier.name,
            company_id=company_id,
            status='PENDING',
            total_items=0,
            subtotal=0,
            tax_total=0,
            total_cost=0.0
        )
        db.session.add(order)
        db.session.commit()
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))
    
    return render_template('purchase/create_purchase.html', suppliers=suppliers, user=user)

# =========================
# DETALLE (Paso 2: Gestionar Productos)
# =========================
@purchase_bp.route('/purchase/<int:order_id>', methods=['GET', 'POST'])
def purchase_detail(order_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    order = PurchaseOrder.query.filter_by(id=order_id, company_id=company_id).first_or_404()
    products = Product.query.filter_by(status=True, company_id=company_id).filter(Product.archived_at.is_(None)).all()
    suppliers = Supplier.query.filter_by(company_id=company_id).filter(Supplier.archived_at.is_(None)).order_by(Supplier.name.asc()).all()
    taxes = _purchase_taxes(company_id)
    uoms = UnitOfMeasure.query.filter_by(company_id=company_id, active=True).order_by(UnitOfMeasure.name.asc()).all()
    variants = ProductVariant.query.filter_by(company_id=company_id, active=True).order_by(ProductVariant.name.asc()).all()
    conversion_rows = ProductUomConversion.query.filter_by(company_id=company_id).all()
    conversions_by_product = {}
    for row in conversion_rows:
        conversions_by_product.setdefault(row.product_id, []).append(row)
    purchase_uom_ids = {}
    for product in products:
        if not product.base_uom:
            purchase_uom_ids[product.id] = []
            continue
        rows = conversions_by_product.get(product.id, [])
        allowed = {product.base_uom.id}
        if rows:
            allowed.update(row.uom_id for row in rows if row.allow_purchase and row.uom and row.uom.active)
        else:
            allowed.update(u.id for u in uoms if u.category == product.base_uom.category)
        if product.purchase_uom_id:
            allowed.add(product.purchase_uom_id)
        purchase_uom_ids[product.id] = sorted(allowed)

    if request.method == 'POST':
        if order.status != 'PENDING':
            flash('No se pueden agregar productos a una orden cerrada.', 'warning')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        product_id = request.form.get('product_id', type=int)
        product = Product.query.filter_by(id=product_id, company_id=company_id, status=True).filter(Product.archived_at.is_(None)).first()
        if not product:
            flash('Selecciona un producto válido del catálogo de tu empresa.', 'danger')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        try:
            unit_cost = _positive_money(request.form.get('unit_cost'), 'El costo unitario')
            tax_id = request.form.get('tax_id', type=int)
            variant_id = request.form.get('variant_id', type=int)
            variant = (
                ProductVariant.query.filter_by(
                    id=variant_id,
                    product_id=product.id,
                    company_id=company_id,
                    active=True,
                ).first()
                if variant_id else None
            )
            if variant_id and not variant:
                raise BusinessRuleError('La variante seleccionada no pertenece al producto.')

            uom_id = request.form.get('uom_id', type=int) or product.purchase_uom_id or product.base_uom_id
            selected_uom = None
            if uom_id:
                selected_uom = UnitOfMeasure.query.filter_by(
                    id=uom_id,
                    company_id=company_id,
                    active=True,
                ).first()
                if not selected_uom:
                    raise BusinessRuleError('La unidad de compra seleccionada no está disponible.')
                allowed_uom_ids = set(purchase_uom_ids.get(product.id, []))
                if allowed_uom_ids and selected_uom.id not in allowed_uom_ids:
                    raise BusinessRuleError(
                        'La unidad seleccionada no está habilitada para comprar este producto. '
                        'Usa su unidad base o una conversión de compra configurada.'
                    )
                if product.base_uom and selected_uom.category != product.base_uom.category:
                    raise BusinessRuleError('La unidad de compra no pertenece a la categoría de medida del producto.')

            quantity = product_quantity(
                request.form.get('quantity'),
                'La cantidad',
                product=product,
                uom=selected_uom,
            )
            base_qty = uom_to_base(product, quantity, uom_id, purpose='purchase')
            uom_factor = base_qty / quantity
        except BusinessRuleError as error:
            flash(str(error), 'danger')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        tax = PurchaseTax.query.filter_by(id=tax_id, company_id=company_id, active=True).first()
        if not tax:
            flash('Selecciona un ITBIS válido.', 'danger')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        item = PurchaseOrderItem.query.filter_by(
            purchase_order_id=order.id, product_id=product_id, variant_id=(variant.id if variant else None), uom_id=uom_id,
            tax_name=tax.name, tax_rate=tax.rate, tax_included=tax.price_included,
        ).first()

        if item:
            item.quantity += quantity
            item.unit_cost = unit_cost
            item.tax_name = tax.name
        else:
            item = PurchaseOrderItem(
                purchase_order_id=order.id, 
                product_id=product_id, variant_id=variant.id if variant else None, uom_id=uom_id, uom_factor=uom_factor,
                quantity=quantity, 
                unit_cost=unit_cost, 
                tax_name=tax.name,
                tax_rate=tax.rate,
                tax_included=tax.price_included,
                quantity_received=0
            )
            db.session.add(item)

        _refresh_order_totals(order)
        db.session.commit()
        
        flash('Producto añadido correctamente.', 'success')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    main_warehouse = Warehouse.query.filter_by(is_main=True, company_id=company_id, status=True).first()
    return render_template(
        'purchase/purchase_detail.html', order=order, products=products,
        items=order.items, user=user, main_warehouse=main_warehouse,
        suppliers=suppliers, taxes=taxes, uoms=uoms, variants=variants, purchase_uom_ids=purchase_uom_ids,
    )


@purchase_bp.route('/purchase/<int:order_id>/save', methods=['POST'])
def save_purchase(order_id):
    company_id = session.get('company_id')
    order = PurchaseOrder.query.filter_by(
        id=order_id, company_id=company_id
    ).with_for_update().first_or_404()
    if order.status != 'PENDING':
        flash('La orden ya está cerrada.', 'warning')
    elif not order.items:
        flash('La orden se guardó como borrador vacío.', 'info')
    else:
        _refresh_order_totals(order)
        db.session.commit()
        flash(f'Orden #{order.id} guardada correctamente.', 'success')
    return redirect(url_for('purchase_bp.purchase_list'))


@purchase_bp.route('/purchase/<int:order_id>/supplier', methods=['POST'])
def update_purchase_supplier(order_id):
    company_id = session.get('company_id')
    order = PurchaseOrder.query.filter_by(
        id=order_id, company_id=company_id
    ).with_for_update().first_or_404()
    if order.status != 'PENDING':
        flash('No puedes cambiar el proveedor de una orden cerrada.', 'warning')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))
    supplier_id = request.form.get('supplier_id', type=int)
    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).filter(Supplier.archived_at.is_(None)).first()
    if not supplier:
        flash('Selecciona un proveedor válido.', 'danger')
    else:
        order.supplier_id = supplier.id
        order.supplier_name = supplier.name
        db.session.commit()
        flash('Proveedor de la orden actualizado.', 'success')
    return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))


@purchase_bp.route('/purchase/taxes/create', methods=['POST'])
def create_purchase_tax():
    company_id = session.get('company_id')
    if not session.get('user_id') or not company_id:
        return {'error': 'Autenticación requerida'}, 401
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    try:
        rate = _tax_rate(data.get('rate'))
    except BusinessRuleError as error:
        return {'error': str(error)}, 400
    if len(name) < 2 or len(name) > 80:
        return {'error': 'Indica un nombre de impuesto válido.'}, 400
    included = bool(data.get('price_included'))
    existing = PurchaseTax.query.filter(
        PurchaseTax.company_id == company_id,
        func.lower(PurchaseTax.name) == name.lower(),
    ).first()
    if existing:
        existing.rate, existing.price_included, existing.active = rate, included, True
        tax = existing
    else:
        tax = PurchaseTax(name=name, rate=rate, price_included=included, company_id=company_id)
        db.session.add(tax)
    db.session.commit()
    return {'id': tax.id, 'name': tax.name, 'rate': float(tax.rate), 'price_included': tax.price_included}


@purchase_bp.route('/purchase/<int:order_id>/tax', methods=['POST'])
def apply_order_tax(order_id):
    company_id = session.get('company_id')
    order = PurchaseOrder.query.filter_by(id=order_id, company_id=company_id).first_or_404()
    if order.status != 'PENDING':
        flash('No puedes cambiar impuestos en una orden cerrada.', 'warning')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))
    tax_id = request.form.get('tax_id', type=int)
    tax = PurchaseTax.query.filter_by(id=tax_id, company_id=company_id, active=True).first()
    if not tax:
        flash('Selecciona un ITBIS válido.', 'danger')
    elif not order.items:
        flash('Agrega productos antes de aplicar un impuesto general.', 'info')
    else:
        for item in order.items:
            item.tax_name = tax.name
            item.tax_rate = tax.rate
            item.tax_included = tax.price_included
        _refresh_order_totals(order)
        db.session.commit()
        flash(f'{tax.name} aplicado a todas las líneas.', 'success')
    return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

# =========================
# RECEPCIÓN DE MERCANCÍA
# =========================
@purchase_bp.route('/purchase/receive/<int:order_id>', methods=['POST'])
def receive_purchase(order_id):
    company_id = session.get('company_id')
    if not session.get('user_id') or not company_id:
        return redirect(url_for('login_bp.login'))
    order = PurchaseOrder.query.filter_by(
        id=order_id, company_id=company_id
    ).with_for_update().first_or_404()

    if order.status != 'PENDING':
        flash('Esta orden ya fue procesada.', 'info')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    main_warehouse = Warehouse.query.filter_by(
        is_main=True, company_id=company_id, status=True
    ).first()
    if not main_warehouse:
        flash('Error: Define un almacén principal primero.', 'danger')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    if not order.items:
        flash('Agrega al menos un producto antes de recibir la orden.', 'warning')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    quantities_to_receive = {}
    tracking_payload = {}
    try:
        for item in order.items:
            pending = as_decimal(item.quantity) - as_decimal(item.quantity_received)
            raw_value = request.form.get(f'receive_{item.id}')
            qty = product_quantity(
                pending if raw_value is None else raw_value,
                f'La cantidad de {item.product.name}',
                product=item.product,
                uom=item.uom,
                allow_zero=True,
            )
            if qty > pending:
                raise BusinessRuleError(f'No puedes recibir más de {pending} de {item.product.name}.')
            quantities_to_receive[item.id] = qty
            if qty <= 0:
                continue

            base_qty = base_quantity_from_factor(qty, item.uom_factor or 1, f'Cantidad base de {item.product.name}')
            tracking = (getattr(item.product, 'tracking', 'NONE') or 'NONE').upper()
            if tracking == 'LOT':
                lot_number = (request.form.get(f'lot_{item.id}') or '').strip()
                if not lot_number:
                    raise BusinessRuleError(f'Indica el lote recibido para {item.product.name}.')
                expires_at = manufactured_at = None
                try:
                    if request.form.get(f'expires_{item.id}'):
                        expires_at = datetime.strptime(request.form.get(f'expires_{item.id}'), '%Y-%m-%d').date()
                    if request.form.get(f'manufactured_{item.id}'):
                        manufactured_at = datetime.strptime(request.form.get(f'manufactured_{item.id}'), '%Y-%m-%d').date()
                except ValueError as exc:
                    raise BusinessRuleError(f'Las fechas del lote de {item.product.name} no son válidas.') from exc
                if manufactured_at and expires_at and expires_at < manufactured_at:
                    raise BusinessRuleError(f'El vencimiento de {item.product.name} no puede ser anterior a su fabricación.')
                tracking_payload[item.id] = ('LOT', lot_number, manufactured_at, expires_at, base_qty)
            elif tracking == 'SERIAL':
                if base_qty != base_qty.to_integral_value():
                    raise BusinessRuleError(f'{item.product.name} usa seriales y solo puede recibirse en unidades enteras.')
                raw_serials = (request.form.get(f'serials_{item.id}') or '').replace(',', '\n')
                serials = []
                for raw in raw_serials.splitlines():
                    value = raw.strip()
                    if value and value not in serials:
                        serials.append(value)
                expected = int(base_qty)
                if len(serials) != expected:
                    raise BusinessRuleError(f'{item.product.name} requiere {expected} serial(es)/IMEI y recibiste {len(serials)}.')
                existing = InventorySerial.query.filter(
                    InventorySerial.company_id == company_id,
                    InventorySerial.serial_number.in_(serials),
                ).first() if serials else None
                if existing:
                    raise BusinessRuleError(f'El serial/IMEI {existing.serial_number} ya está registrado.')
                tracking_payload[item.id] = ('SERIAL', serials, base_qty)
    except BusinessRuleError as error:
        db.session.rollback()
        flash(str(error), 'danger')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    try:
        for item in order.items:
            qty = quantities_to_receive[item.id]
            if qty <= 0:
                continue

            item.quantity_received = as_decimal(item.quantity_received) + qty
            base_qty = base_quantity_from_factor(qty, item.uom_factor or 1, f'Cantidad base de {item.product.name}')

            # Costeo antes de incorporar la recepción al stock físico.
            unit_base_cost = (as_decimal(item.unit_cost) / as_decimal(item.uom_factor or 1)).quantize(finite_decimal('0.0001'))
            register_receipt_cost(
                item.product, main_warehouse.id, base_qty, unit_base_cost,
                variant_id=item.variant_id, purchase_item_id=item.id,
            )

            stock = WarehouseStock.query.filter_by(
                product_id=item.product_id, warehouse_id=main_warehouse.id, company_id=company_id
            ).with_for_update().first()
            if stock:
                stock.quantity = as_decimal(stock.quantity) + base_qty
            else:
                stock = WarehouseStock(
                    product_id=item.product_id, warehouse_id=main_warehouse.id,
                    quantity=base_qty, company_id=company_id,
                )
                db.session.add(stock)
            if item.variant_id:
                variant_stock = WarehouseVariantStock.query.filter_by(
                    company_id=company_id, warehouse_id=main_warehouse.id, variant_id=item.variant_id
                ).with_for_update().first()
                if not variant_stock:
                    variant_stock = WarehouseVariantStock(
                        company_id=company_id, warehouse_id=main_warehouse.id,
                        product_id=item.product_id, variant_id=item.variant_id, quantity=0,
                    )
                    db.session.add(variant_stock)
                variant_stock.quantity = as_decimal(variant_stock.quantity) + base_qty

            payload = tracking_payload.get(item.id)
            if payload and payload[0] == 'LOT':
                _, lot_number, manufactured_at, expires_at, tracked_qty = payload
                lot_query = InventoryLot.query.filter_by(
                    company_id=company_id, product_id=item.product_id,
                    warehouse_id=main_warehouse.id, lot_number=lot_number,
                )
                lot_query = lot_query.filter_by(variant_id=item.variant_id) if item.variant_id else lot_query.filter(InventoryLot.variant_id.is_(None))
                lot = lot_query.with_for_update().first()
                if not lot:
                    lot = InventoryLot(
                        company_id=company_id, product_id=item.product_id, variant_id=item.variant_id,
                        warehouse_id=main_warehouse.id, lot_number=lot_number, quantity=0,
                        manufactured_at=manufactured_at, expires_at=expires_at, status='AVAILABLE',
                    )
                    db.session.add(lot)
                elif lot.expires_at and expires_at and lot.expires_at != expires_at:
                    raise BusinessRuleError(f'El lote {lot_number} ya existe con otra fecha de vencimiento.')
                lot.quantity = as_decimal(lot.quantity) + tracked_qty
                lot.manufactured_at = lot.manufactured_at or manufactured_at
                lot.expires_at = lot.expires_at or expires_at
                lot.status = 'AVAILABLE'
            elif payload and payload[0] == 'SERIAL':
                _, serials, _ = payload
                for serial_number in serials:
                    db.session.add(InventorySerial(
                        company_id=company_id, product_id=item.product_id, variant_id=item.variant_id,
                        warehouse_id=main_warehouse.id, serial_number=serial_number, status='AVAILABLE',
                    ))

            db.session.add(StockMovement(
                product_id=item.product_id, warehouse_id=main_warehouse.id, company_id=company_id,
                user_id=session.get('user_id'), movement_type='IN', quantity=base_qty, reason=f'Recepción OC #{order.id}'
            ))

        # Verificar si se completó la orden
        if all(i.quantity_received >= i.quantity for i in order.items):
            order.status = 'RECEIVED'
            internal_document = f'AUTO-OC-{order.id}'
            if not SupplierBill.query.filter_by(company_id=company_id, purchase_order_id=order.id).first():
                db.session.add(SupplierBill(
                    company_id=company_id, supplier_id=order.supplier_id, purchase_order_id=order.id,
                    document_number=internal_document, amount=order.total_cost or 0,
                    due_date=(datetime.now() + timedelta(days=30)).date(),
                    notes='Cuenta generada automáticamente al recibir la orden.',
                ))

        db.session.commit()
    except (BusinessRuleError, NumericValueError) as exc:
        db.session.rollback()
        flash(f'No se registró la recepción: {exc}', 'danger')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning(
            'Purchase receipt integrity conflict request_id=%s company_id=%s order_id=%s',
            getattr(g, 'request_id', None), company_id, order.id, exc_info=True,
        )
        flash(
            'No se registró la recepción porque un lote, serial o movimiento ya existe. '
            'Revisa los datos capturados; el inventario y la orden quedaron sin cambios.',
            'danger',
        )
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))
    except Exception:
        db.session.rollback()
        request_id = getattr(g, 'request_id', None)
        current_app.logger.exception(
            'Unexpected purchase receipt failure request_id=%s company_id=%s order_id=%s',
            request_id, company_id, order.id,
        )
        reference = f' Referencia: {request_id}.' if request_id else ''
        flash(
            'No se registró la recepción por un error interno. Ningún stock, costo, lote, serial '
            f'ni cuenta por pagar fue confirmado.{reference}',
            'danger',
        )
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))
    flash('Entrada de almacén registrada con éxito.', 'success')
    return redirect(url_for('purchase_bp.purchase_list'))

# =========================
# ELIMINAR ITEM
# =========================
@purchase_bp.route('/purchase/item/delete/<int:item_id>', methods=['POST'])
def delete_purchase_item(item_id):
    company_id = session.get('company_id')
    item = PurchaseOrderItem.query.join(PurchaseOrder).filter(
        PurchaseOrderItem.id == item_id,
        PurchaseOrder.company_id == company_id,
    ).first_or_404()
    order = item.purchase_order

    if order.status != 'PENDING':
        abort(403)

    db.session.delete(item)
    _refresh_order_totals(order)
    db.session.commit()
    
    flash('Producto eliminado de la orden.', 'info')
    return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

# =========================
# CANCELAR ORDEN
# =========================
@purchase_bp.route('/purchase/cancel/<int:order_id>', methods=['POST'])
def cancel_purchase(order_id):
    company_id = session.get('company_id')
    order = PurchaseOrder.query.filter_by(
        id=order_id, company_id=company_id
    ).with_for_update().first_or_404()
    
    if order.status == 'PENDING':
        order.status = 'CANCELLED'
        db.session.commit()
        flash(f'Orden #{order.id} cancelada correctamente.', 'success')
    else:
        flash('No se puede cancelar una orden ya recibida.', 'warning')
        
    return redirect(url_for('purchase_bp.purchase_list'))
