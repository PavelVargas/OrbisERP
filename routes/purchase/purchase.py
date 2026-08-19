from flask import Blueprint, render_template, redirect, url_for, request, abort, flash, session
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
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import joinedload, selectinload

purchase_bp = Blueprint('purchase_bp', __name__)

def _positive_integer(raw_value, field_name):
    """Accept browser values such as 1 or 1.00, but reject fractional units."""
    try:
        value = Decimal(str(raw_value or '').strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f'{field_name} no es válido.')
    if not value.is_finite() or value <= 0 or value != value.to_integral_value():
        raise ValueError(f'{field_name} debe ser un número entero mayor que cero.')
    return int(value)

def _positive_money(raw_value, field_name):
    try:
        value = Decimal(str(raw_value or '').strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f'{field_name} no es válido.')
    if not value.is_finite() or value <= 0:
        raise ValueError(f'{field_name} debe ser mayor que cero.')
    return value.quantize(Decimal('0.01'))

def _refresh_order_totals(order):
    db.session.flush()
    items = PurchaseOrderItem.query.filter_by(purchase_order_id=order.id).all()
    order.total_items = sum(int(item.quantity or 0) for item in items)
    order.subtotal = sum((item.net_subtotal for item in items), Decimal('0.00')).quantize(Decimal('0.01'))
    order.tax_total = sum((item.tax_amount for item in items), Decimal('0.00')).quantize(Decimal('0.01'))
    order.total_cost = sum((item.line_total for item in items), Decimal('0.00')).quantize(Decimal('0.01'))


def _purchase_taxes(company_id):
    """Create safe defaults once and return the company's active purchase taxes."""
    taxes = PurchaseTax.query.filter_by(company_id=company_id, active=True).order_by(
        PurchaseTax.rate.asc(), PurchaseTax.price_included.asc(), PurchaseTax.name.asc()
    ).all()
    defaults = (
        ('ITBIS exento', Decimal('0.00'), False),
        ('ITBIS 18% no incluido', Decimal('18.00'), False),
        ('ITBIS 18% incluido', Decimal('18.00'), True),
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
        'invested': sum((Decimal(order.total_cost or 0) for order in all_orders if order.status == 'RECEIVED'), Decimal('0.00')),
    }
    suppliers = Supplier.query.filter_by(company_id=company_id).order_by(Supplier.name.asc()).all()
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
    suppliers = Supplier.query.filter_by(company_id=company_id).order_by(Supplier.name.asc()).all()
    
    if request.method == 'POST':
        # Conversión a int() para evitar error de PostgreSQL
        supplier_id = request.form.get('supplier_id', type=int)
        if not supplier_id:
            flash('Selecciona o crea un proveedor válido.', 'warning')
            return redirect(request.url)
        supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).first_or_404()
        
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
    products = Product.query.filter_by(status=True, company_id=company_id).all()
    suppliers = Supplier.query.filter_by(company_id=company_id).order_by(Supplier.name.asc()).all()
    taxes = _purchase_taxes(company_id)

    if request.method == 'POST':
        if order.status != 'PENDING':
            flash('No se pueden agregar productos a una orden cerrada.', 'warning')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        product_id = request.form.get('product_id', type=int)
        product = Product.query.filter_by(id=product_id, company_id=company_id, status=True).first()
        if not product:
            flash('Selecciona un producto válido del catálogo de tu empresa.', 'danger')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        try:
            quantity = _positive_integer(request.form.get('quantity'), 'La cantidad')
            unit_cost = _positive_money(request.form.get('unit_cost'), 'El costo unitario')
            tax_id = request.form.get('tax_id', type=int)
        except ValueError as error:
            flash(str(error), 'danger')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        tax = PurchaseTax.query.filter_by(id=tax_id, company_id=company_id, active=True).first()
        if not tax:
            flash('Selecciona un ITBIS válido.', 'danger')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        item = PurchaseOrderItem.query.filter_by(
            purchase_order_id=order.id, product_id=product_id,
            tax_name=tax.name, tax_rate=tax.rate, tax_included=tax.price_included,
        ).first()

        if item:
            item.quantity += quantity
            item.unit_cost = unit_cost
            item.tax_name = tax.name
        else:
            item = PurchaseOrderItem(
                purchase_order_id=order.id, 
                product_id=product_id,
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
        suppliers=suppliers, taxes=taxes,
    )


@purchase_bp.route('/purchase/<int:order_id>/save', methods=['POST'])
def save_purchase(order_id):
    company_id = session.get('company_id')
    order = PurchaseOrder.query.filter_by(id=order_id, company_id=company_id).first_or_404()
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
    order = PurchaseOrder.query.filter_by(id=order_id, company_id=company_id).first_or_404()
    if order.status != 'PENDING':
        flash('No puedes cambiar el proveedor de una orden cerrada.', 'warning')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))
    supplier_id = request.form.get('supplier_id', type=int)
    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).first()
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
        rate = Decimal(str(data.get('rate', '')).strip()).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return {'error': 'El porcentaje no es válido.'}, 400
    if len(name) < 2 or len(name) > 80 or not rate.is_finite() or rate < 0 or rate > 100:
        return {'error': 'Indica un nombre válido y una tasa entre 0% y 100%.'}, 400
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
    order = PurchaseOrder.query.filter_by(id=order_id, company_id=company_id).first_or_404()

    if order.status != 'PENDING':
        flash('Esta orden ya fue procesada.', 'info')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    main_warehouse = Warehouse.query.filter_by(is_main=True, company_id=company_id).first()
    if not main_warehouse:
        flash('Error: Define un almacén principal primero.', 'danger')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    if not order.items:
        flash('Agrega al menos un producto antes de recibir la orden.', 'warning')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    quantities_to_receive = {}
    try:
        for item in order.items:
            pending = int(item.quantity or 0) - int(item.quantity_received or 0)
            raw_value = request.form.get(f'receive_{item.id}')
            qty = _positive_integer(raw_value, f'La cantidad de {item.product.name}') if raw_value else pending
            if qty > pending:
                raise ValueError(f'No puedes recibir más de {pending} unidades de {item.product.name}.')
            quantities_to_receive[item.id] = qty
    except ValueError as error:
        flash(str(error), 'danger')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    for item in order.items:
        # Si es via POST manual (recibir parcial)
        qty = quantities_to_receive[item.id]
        if qty <= 0:
            continue

        item.quantity_received += qty

        # Actualizar Stock
        stock = WarehouseStock.query.filter_by(
            product_id=item.product_id, warehouse_id=main_warehouse.id, company_id=company_id
        ).first()

        if stock:
            stock.quantity += qty
        else:
            stock = WarehouseStock(
                product_id=item.product_id, 
                warehouse_id=main_warehouse.id,
                quantity=qty, 
                company_id=company_id
            )
            db.session.add(stock)

        # Registrar Movimiento
        db.session.add(StockMovement(
            product_id=item.product_id, warehouse_id=main_warehouse.id, company_id=company_id,
            movement_type='IN', quantity=qty, reason=f'Recepción OC #{order.id}'
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
    flash('Entrada de almacén registrada con éxito.', 'success')
    return redirect(url_for('purchase_bp.purchase_list'))

# =========================
# ELIMINAR ITEM
# =========================
@purchase_bp.route('/purchase/item/delete/<int:item_id>', methods=['POST'])
def delete_purchase_item(item_id):
    company_id = session.get('company_id')
    item = PurchaseOrderItem.query.get_or_404(item_id)
    order = item.purchase_order
    
    if order.company_id != company_id or order.status != 'PENDING':
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
    order = PurchaseOrder.query.filter_by(id=order_id, company_id=company_id).first_or_404()
    
    if order.status == 'PENDING':
        order.status = 'CANCELLED'
        db.session.commit()
        flash(f'Orden #{order.id} cancelada correctamente.', 'success')
    else:
        flash('No se puede cancelar una orden ya recibida.', 'warning')
        
    return redirect(url_for('purchase_bp.purchase_list'))
