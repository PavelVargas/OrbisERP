from flask import Blueprint, render_template, redirect, url_for, request, abort, flash, session
from models.purchase.purchase_order import PurchaseOrder
from models.purchase.purchase_order_item import PurchaseOrderItem
from models.stock_movement.stock_movement import StockMovement
from models.products.products import Product
from models.supplier.supplier import Supplier
from models.user.user import User
from db import db
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from decimal import Decimal

purchase_bp = Blueprint('purchase_bp', __name__)

# =========================
# LISTA DE ÓRDENES
# =========================
@purchase_bp.route('/purchase')
def purchase_list():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    orders = PurchaseOrder.query.filter_by(company_id=company_id).order_by(PurchaseOrder.created_at.desc()).all()
    
    return render_template('purchase/purchase_list.html', orders=orders, user=user)

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
        supplier_id = int(request.form.get('supplier_id'))
        supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).first_or_404()
        
        order = PurchaseOrder(
            supplier_id=supplier.id, 
            supplier_name=supplier.name,
            company_id=company_id,
            status='PENDING',
            total_items=0,
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

    if request.method == 'POST':
        if order.status != 'PENDING':
            flash('No se pueden agregar productos a una orden cerrada.', 'warning')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        product_id = int(request.form.get('product_id'))
        quantity = int(request.form.get('quantity', 0))
        # Si no envías unit_cost desde el HTML, asegúrate de manejar un default o capturarlo
        unit_cost_raw = request.form.get('unit_cost', '0')
        unit_cost = Decimal(unit_cost_raw)

        if quantity <= 0:
            flash('La cantidad debe ser mayor a cero.', 'danger')
            return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

        item = PurchaseOrderItem.query.filter_by(
            purchase_order_id=order.id, product_id=product_id
        ).first()

        if item:
            item.quantity += quantity
            item.unit_cost = unit_cost
        else:
            item = PurchaseOrderItem(
                purchase_order_id=order.id, 
                product_id=product_id,
                quantity=quantity, 
                unit_cost=unit_cost, 
                quantity_received=0
            )
            db.session.add(item)

        db.session.commit()
        
        # Actualizar totales de la orden
        order.total_items = sum(i.quantity for i in order.items)
        order.total_cost = sum((i.unit_cost * i.quantity) for i in order.items)
        db.session.commit()
        
        flash('Producto añadido correctamente.', 'success')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    return render_template('purchase/purchase_detail.html', order=order, products=products, items=order.items, user=user)

# =========================
# RECEPCIÓN DE MERCANCÍA
# =========================
@purchase_bp.route('/purchase/receive/<int:order_id>', methods=['POST', 'GET'])
def receive_purchase(order_id):
    company_id = session.get('company_id')
    order = PurchaseOrder.query.filter_by(id=order_id, company_id=company_id).first_or_404()

    if order.status != 'PENDING':
        flash('Esta orden ya fue procesada.', 'info')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    main_warehouse = Warehouse.query.filter_by(is_main=True, company_id=company_id).first()
    if not main_warehouse:
        flash('Error: Define un almacén principal primero.', 'danger')
        return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

    for item in order.items:
        # Si es via POST manual (recibir parcial)
        qty_val = request.form.get(f'receive_{item.id}')
        if qty_val:
            qty = int(qty_val)
        else:
            # Si se hace click en el botón general, recibimos todo el pendiente
            qty = item.quantity - item.quantity_received

        if qty <= 0: continue

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

    db.session.commit()
    flash('Entrada de almacén registrada con éxito.', 'success')
    return redirect(url_for('purchase_bp.purchase_list'))

# =========================
# ELIMINAR ITEM
# =========================
@purchase_bp.route('/purchase/item/delete/<int:item_id>')
def delete_purchase_item(item_id):
    company_id = session.get('company_id')
    item = PurchaseOrderItem.query.get_or_404(item_id)
    order = item.purchase_order
    
    if order.company_id != company_id or order.status != 'PENDING':
        abort(403)

    db.session.delete(item)
    db.session.commit()
    
    order.total_items = sum(i.quantity for i in order.items)
    order.total_cost = sum((i.unit_cost * i.quantity) for i in order.items)
    db.session.commit()
    
    flash('Producto eliminado de la orden.', 'info')
    return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))

# =========================
# CANCELAR ORDEN
# =========================
@purchase_bp.route('/purchase/cancel/<int:order_id>')
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