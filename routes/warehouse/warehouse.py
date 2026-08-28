import io
import re
from uuid import uuid4

from barcode import Code128
from barcode.writer import ImageWriter
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, session, send_file
from db import db
from models.products.products import Product, ProductType
from models.warehouse.warehouse import Warehouse
from models.warehouse_location.warehouse_location import LocationMovement, LocationStock, WarehouseLocation
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.stock_transfer.stock_transfer import StockTransfer
from models.user.user import User
from services.validation import BusinessRuleError, tenant_id
from services.quantity import product_quantity, as_decimal
from sqlalchemy.exc import SQLAlchemyError

warehouse_bp = Blueprint('warehouse_bp', __name__, url_prefix='/warehouses')

# =========================
# LISTAR ALMACENES
# =========================
@warehouse_bp.route('/')
def list_warehouses():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    # Verificación de login
    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    
    # Si hay una empresa en sesión (Admin o Superadmin gestionando una empresa)
    if company_id:
        # Filtramos estrictamente por la empresa de la sesión
        query = Warehouse.query.filter_by(company_id=company_id, status=True)

        if user.role in ['admin', 'superadmin']:
            warehouses = query.all()
        elif user.warehouse_id:
            # Si es usuario staff, solo ve su almacén asignado si pertenece a esa empresa
            warehouses = query.filter_by(id=user.warehouse_id).all()
        else:
            warehouses = []
    else:
        # Si no hay company_id en sesión, no hay nada que mostrar bajo este filtro
        warehouses = []
        
    return render_template(
        'warehouse/list.html', 
        warehouses=warehouses, 
        user_role=user.role,
        user_warehouse_id=user.warehouse_id,
        user=user
    )

# =========================
# CREAR ALMACÉN CON LÍMITES
# =========================
@warehouse_bp.route('/create_warehouse', methods=['GET', 'POST'])
def create_warehouse():
    company_id = session.get('company_id')
    user_id = session.get('user_id')

    if not user_id or not company_id:
        flash('Acceso restringido: No se detectó una empresa activa.', 'warning')
        return redirect(url_for('warehouse_bp.list_warehouses'))

    user = User.query.get_or_404(user_id)
    
    # 1. Obtener la empresa y sus límites (Importación local para evitar circularidad)
    from models.company.company import Company
    company = Company.query.get(company_id)
    
    # Prevenir error si la empresa no existe
    plan_limits = company.get_plan_limits() if company else {'max_warehouses': 0}
    plan_name = company.plan_name if company else "Sin Plan"

    # 2. Contar almacenes actuales de la empresa
    current_wares_count = Warehouse.query.filter_by(company_id=company_id, status=True).count()

    # Seguridad: Solo admin o superadmin
    if not user.has_permission('warehouses.create'):
        flash('Acceso denegado: Solo administradores', 'danger')
        return redirect(url_for('warehouse_bp.list_warehouses'))

    if request.method == 'POST':
        # 3. VALIDACIÓN DE LÍMITE DE PLAN (El Superadmin ignora esta restricción si quieres)
        if user.role != 'superadmin':
            if current_wares_count >= plan_limits['max_warehouses']:
                flash(f"Límite alcanzado para el plan {plan_name}. Máximo: {plan_limits['max_warehouses']}.", 'warning')
                return redirect(url_for('warehouse_bp.list_warehouses'))

        name = (request.form.get('name') or '').strip()
        location = (request.form.get('location') or '').strip() or None
        if not name or len(name) > 150:
            flash('El nombre del almacén es obligatorio y admite hasta 150 caracteres.', 'danger')
            return redirect(url_for('warehouse_bp.create_warehouse'))
        if location and len(location) > 255:
            flash('La ubicación admite hasta 255 caracteres.', 'danger')
            return redirect(url_for('warehouse_bp.create_warehouse'))

        is_main = (current_wares_count == 0)

        warehouse = Warehouse(
            name=name,
            location=location,
            is_main=is_main,
            status=True,
            company_id=company_id
        )
        
        try:
            db.session.add(warehouse)
            db.session.commit()
            flash(f'Almacén "{name}" creado correctamente', 'success')
            return redirect(url_for('warehouse_bp.list_warehouses'))
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('No se pudo crear el almacén para la empresa %s', company_id)
            flash('No se pudo crear el almacén. Revisa que sus datos no estén duplicados.', 'danger')

    return render_template('warehouse/create.html', user=user, plan_limits=plan_limits, current_count=current_wares_count)

# =========================
# EDITAR ALMACÉN
# =========================
@warehouse_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_warehouse(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get_or_404(user_id)
    
    if not user.has_permission('warehouses.edit'):
        flash('Acceso denegado', 'danger')
        return redirect(url_for('warehouse_bp.list_warehouses'))

    # Seguridad: El almacén debe pertenecer a la empresa activa en la sesión
    warehouse = Warehouse.query.filter_by(id=id, company_id=company_id).first_or_404()
    
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        location = (request.form.get('location') or '').strip() or None
        if not name or len(name) > 150:
            flash('El nombre del almacén es obligatorio y admite hasta 150 caracteres.', 'danger')
            return redirect(url_for('warehouse_bp.edit_warehouse', id=warehouse.id))
        if location and len(location) > 255:
            flash('La ubicación admite hasta 255 caracteres.', 'danger')
            return redirect(url_for('warehouse_bp.edit_warehouse', id=warehouse.id))
        warehouse.name = name
        warehouse.location = location
        try:
            db.session.commit()
            flash('Almacén actualizado correctamente', 'success')
            return redirect(url_for('warehouse_bp.list_warehouses'))
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('No se pudo actualizar el almacén %s', warehouse.id)
            flash('No se pudo actualizar el almacén. Revisa los datos e inténtalo nuevamente.', 'danger')
        
    return render_template('warehouse/edit.html', warehouse=warehouse, user=user)

# =========================
# VER STOCK DE ALMACÉN
# =========================
@warehouse_bp.route('/<int:id>/stock')
def warehouse_stock(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)

    # Validar que el almacén exista y pertenezca a la empresa en sesión
    warehouse = Warehouse.query.filter_by(id=id, company_id=company_id).first_or_404()

    # Seguridad de rol
    if user.role not in ['admin', 'superadmin'] and user.warehouse_id != id:
        flash('No tienes permiso para ver este stock', 'danger')
        return redirect(url_for('warehouse_bp.list_warehouses'))

    # Obtener stock
    stocks = WarehouseStock.query.filter_by(warehouse_id=id, company_id=company_id).all()
    
    return render_template('warehouse/stock.html', warehouse=warehouse, stocks=stocks, user=user)


def _location_code(value):
    return re.sub(r'[^A-Z0-9-]+', '-', (value or '').strip().upper()).strip('-')[:50]


@warehouse_bp.route('/<int:warehouse_id>/locations', methods=['GET', 'POST'])
def warehouse_locations(warehouse_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = db.session.get(User, user_id)
    warehouse = Warehouse.query.filter_by(id=warehouse_id, company_id=company_id, status=True).first_or_404()
    if user.role not in ['admin', 'superadmin'] and user.warehouse_id != warehouse.id:
        flash('No tienes permiso para gestionar estas ubicaciones.', 'danger')
        return redirect(url_for('warehouse_bp.list_warehouses'))

    locations = WarehouseLocation.query.filter_by(
        warehouse_id=warehouse.id,
        company_id=company_id,
        status=True,
    ).order_by(WarehouseLocation.parent_id.asc().nullsfirst(), WarehouseLocation.name.asc()).all()
    locations.sort(key=lambda row: row.full_path.casefold())

    if request.method == 'POST':
        if not user.has_permission('locations.manage'):
            flash('Solo un administrador puede crear ubicaciones.', 'danger')
            return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=warehouse.id))

        name = (request.form.get('name') or '').strip()
        code = _location_code(request.form.get('code') or name)
        description = (request.form.get('description') or '').strip() or None
        parent_id = request.form.get('parent_id', type=int)
        if not name or not code:
            flash('El nombre y el código de la ubicación son obligatorios.', 'danger')
            return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=warehouse.id))

        parent = None
        if parent_id:
            parent = WarehouseLocation.query.filter_by(
                id=parent_id,
                warehouse_id=warehouse.id,
                company_id=company_id,
                status=True,
            ).first()
            if not parent:
                flash('La ubicación superior no es válida.', 'danger')
                return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=warehouse.id))

        if WarehouseLocation.query.filter_by(warehouse_id=warehouse.id, code=code).first():
            flash('Ese código ya existe dentro del almacén.', 'danger')
            return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=warehouse.id))

        barcode = f'LOC-{company_id}-{warehouse.id}-{code}-{uuid4().hex[:6].upper()}'
        location = WarehouseLocation(
            name=name,
            code=code,
            barcode=barcode,
            description=description,
            parent=parent,
            warehouse_id=warehouse.id,
            company_id=company_id,
            status=True,
        )
        try:
            db.session.add(location)
            db.session.commit()
            flash(f'Ubicación “{location.full_path}” creada. Su código ya puede escanearse.', 'success')
        except Exception:
            db.session.rollback()
            flash('No se pudo crear la ubicación. Revisa que el código no esté repetido.', 'danger')
        return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=warehouse.id))

    products = Product.query.filter_by(company_id=company_id, status=True).filter(
        Product.product_type != ProductType.SERVICE
    ).order_by(Product.name.asc()).all()
    aggregate_stocks = {
        row.product_id: as_decimal(row.quantity)
        for row in WarehouseStock.query.filter_by(warehouse_id=warehouse.id, company_id=company_id).all()
    }
    allocated = {}
    for row in LocationStock.query.join(WarehouseLocation).filter(
        WarehouseLocation.warehouse_id == warehouse.id,
        LocationStock.company_id == company_id,
    ).all():
        allocated[row.product_id] = allocated.get(row.product_id, as_decimal(0)) + as_decimal(row.quantity)
    reserved = {}
    reserved_rows = db.session.query(
        StockTransfer.product_id,
        db.func.coalesce(db.func.sum(StockTransfer.quantity), 0),
    ).filter(
        StockTransfer.company_id == company_id,
        StockTransfer.from_warehouse_id == warehouse.id,
        StockTransfer.from_location_id.is_(None),
        StockTransfer.status == 'PENDING',
    ).group_by(StockTransfer.product_id).all()
    for product_id, quantity in reserved_rows:
        reserved[product_id] = as_decimal(quantity or 0)
    unassigned = {
        product_id: max(quantity - allocated.get(product_id, 0) - reserved.get(product_id, 0), 0)
        for product_id, quantity in aggregate_stocks.items()
    }

    return render_template(
        'warehouse/locations.html',
        warehouse=warehouse,
        locations=locations,
        products=products,
        unassigned=unassigned,
        user=user,
    )


@warehouse_bp.route('/locations/<int:location_id>/allocate', methods=['POST'])
def allocate_location_stock(location_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    user = db.session.get(User, user_id) if user_id else None
    if not user or not company_id or not user.has_permission('locations.allocate'):
        flash('No tienes permiso para distribuir existencias.', 'danger')
        return redirect(url_for('warehouse_bp.list_warehouses'))

    location = WarehouseLocation.query.filter_by(id=location_id, company_id=company_id, status=True).first_or_404()
    try:
        product_id = tenant_id(request.form.get('product_id'), 'Producto')
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=location.warehouse_id))

    product = Product.query.filter_by(id=product_id, company_id=company_id, status=True).filter(Product.archived_at.is_(None)).first()
    if not product or product.product_type == ProductType.SERVICE:
        flash('El producto no es válido para inventario.', 'danger')
        return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=location.warehouse_id))

    try:
        quantity = product_quantity(request.form.get('quantity'), 'Cantidad', product=product, uom=product.base_uom)
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=location.warehouse_id))

    warehouse_stock = WarehouseStock.query.filter_by(
        warehouse_id=location.warehouse_id,
        product_id=product_id,
        company_id=company_id,
    ).with_for_update().first()
    allocated = db.session.query(db.func.coalesce(db.func.sum(LocationStock.quantity), 0)).join(
        WarehouseLocation, LocationStock.location_id == WarehouseLocation.id
    ).filter(
        WarehouseLocation.warehouse_id == location.warehouse_id,
        LocationStock.product_id == product_id,
        LocationStock.company_id == company_id,
    ).scalar()
    reserved = db.session.query(db.func.coalesce(db.func.sum(StockTransfer.quantity), 0)).filter(
        StockTransfer.company_id == company_id,
        StockTransfer.product_id == product_id,
        StockTransfer.from_warehouse_id == location.warehouse_id,
        StockTransfer.from_location_id.is_(None),
        StockTransfer.status == 'PENDING',
    ).scalar()
    available = as_decimal(warehouse_stock.quantity) - as_decimal(allocated or 0) - as_decimal(reserved or 0) if warehouse_stock else as_decimal(0)
    if quantity > available:
        flash(f'Solo quedan {available} unidades sin ubicación asignada.', 'danger')
        return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=location.warehouse_id))

    row = LocationStock.query.filter_by(
        location_id=location.id, product_id=product_id, company_id=company_id
    ).with_for_update().first()
    if not row:
        row = LocationStock(location_id=location.id, product_id=product_id, company_id=company_id, quantity=0)
        db.session.add(row)
    row.quantity += quantity
    db.session.add(LocationMovement(
        movement_type='ALLOCATION', quantity=quantity, balance_after=row.quantity,
        reference='ASIGNACION', notes='Asignación inicial desde stock general',
        location_id=location.id, product_id=product_id, company_id=company_id, user_id=user.id,
    ))
    db.session.commit()
    flash(f'{quantity} unidades asignadas a {location.full_path}.', 'success')
    return redirect(url_for('warehouse_bp.warehouse_locations', warehouse_id=location.warehouse_id))


@warehouse_bp.route('/locations/<int:location_id>/barcode.png')
def location_barcode(location_id):
    company_id = session.get('company_id')
    location = WarehouseLocation.query.filter_by(id=location_id, company_id=company_id, status=True).first_or_404()
    buffer = io.BytesIO()
    Code128(location.barcode, writer=ImageWriter()).write(
        buffer,
        options={'module_height': 12, 'font_size': 9, 'text_distance': 3, 'quiet_zone': 3},
    )
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png', download_name=f'{location.code}.png')


@warehouse_bp.route('/locations/<int:location_id>/traceability')
def location_traceability(location_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))
    user = db.session.get(User, user_id)
    location = WarehouseLocation.query.filter_by(id=location_id, company_id=company_id, status=True).first_or_404()
    if user.role not in ['admin', 'superadmin'] and user.warehouse_id != location.warehouse_id:
        flash('No tienes permiso para consultar esta ubicación.', 'danger')
        return redirect(url_for('warehouse_bp.list_warehouses'))
    movements = LocationMovement.query.filter_by(
        location_id=location.id, company_id=company_id
    ).order_by(LocationMovement.created_at.desc()).all()
    pending_in = StockTransfer.query.filter_by(to_location_id=location.id, company_id=company_id, status='PENDING').all()
    pending_out = StockTransfer.query.filter_by(from_location_id=location.id, company_id=company_id, status='PENDING').all()
    stocks = LocationStock.query.filter_by(location_id=location.id, company_id=company_id).filter(LocationStock.quantity > 0).all()
    return render_template('warehouse/location_traceability.html', location=location, movements=movements,
                           pending_in=pending_in, pending_out=pending_out, stocks=stocks, user=user)
