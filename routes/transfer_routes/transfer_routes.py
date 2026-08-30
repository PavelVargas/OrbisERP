from services.numeric import NumericValueError, finite_decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from models.stock_transfer.stock_transfer import StockTransfer
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.warehouse_location.warehouse_location import LocationMovement, LocationStock, WarehouseLocation
from models.products.products import Product, ProductType
from models.stock_movement.stock_movement import StockMovement
from models.user.user import User
from models.retail import ProductBarcode
from db import db
from decimal import Decimal
from datetime import datetime
from flask import render_template, make_response
from services.transfer_pdf import build_transfer_pdf
import re
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from services.validation import BusinessRuleError, tenant_id
from services.quantity import product_quantity, as_decimal, display_quantity

transfer_bp = Blueprint('transfer_bp', __name__, url_prefix='/transfers')

def _same_inventory_point(from_warehouse_id, from_location_id, to_warehouse_id, to_location_id):
    """General stock and every nested location are separate inventory nodes."""
    return from_warehouse_id == to_warehouse_id and from_location_id == to_location_id


def _receive_redirect_url(transfer=None):
    """Return only to known internal transfer views after a receive attempt."""
    target = (request.form.get('return_to') or '').strip().lower()
    if target == 'scanner':
        return url_for('transfer_bp.scanner_mode')
    if target == 'warehouse' and transfer is not None:
        return url_for('transfer_bp.transfers_by_warehouse', warehouse_id=transfer.to_warehouse_id)
    return url_for('transfer_bp.transfers')

# ==========================================
# LISTAR TODAS LAS TRANSFERENCIAS
# ==========================================
@transfer_bp.route('/')
def transfers():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.filter_by(id=user_id, company_id=company_id).first_or_404()
    products = Product.query.filter_by(company_id=company_id, status=True).filter(Product.archived_at.is_(None)).all()
    warehouses = Warehouse.query.filter_by(company_id=company_id, status=True).all()
    # El centro funciona como una bandeja de trabajo: una operación recibida
    # conserva su trazabilidad, pero ya no debe seguir apareciendo como pendiente.
    transfers_list = StockTransfer.query.filter_by(
        company_id=company_id,
        status='PENDING',
    ).order_by(StockTransfer.created_at.desc()).all()

    return render_template(
        'transfers/list.html',
        user=user,
        products=products,
        warehouses=warehouses,
        transfers=transfers_list
    )

# ==========================================
# CREAR TRANSFERENCIA (QUEDA EN ESTADO PENDING)
# ==========================================
@transfer_bp.route('/create', methods=['GET', 'POST'])
def create_transfer():
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.filter_by(id=user_id, company_id=company_id).first()
    if not user:
        session.clear()
        return redirect(url_for('login_bp.login'))

    if request.method == 'POST':
        from_wh = request.form.get('from_warehouse', type=int)
        to_wh = request.form.get('to_warehouse', type=int)
        from_location_id = request.form.get('from_location_id', type=int)
        to_location_id = request.form.get('to_location_id', type=int)
        product_ids = request.form.getlist('product_ids[]')
        quantities = request.form.getlist('quantities[]')

        origin = Warehouse.query.filter_by(id=from_wh, company_id=company_id, status=True).first()
        destination = Warehouse.query.filter_by(id=to_wh, company_id=company_id, status=True).first()
        if not origin or not destination:
            flash('Selecciona almacenes válidos de la empresa activa.', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))

        from_location = None
        if from_location_id:
            from_location = WarehouseLocation.query.filter_by(
                id=from_location_id, warehouse_id=from_wh, company_id=company_id, status=True
            ).first()
            if not from_location:
                flash('La ubicación de origen no pertenece al almacén seleccionado.', 'danger')
                return redirect(url_for('transfer_bp.create_transfer'))

        to_location = None
        if to_location_id:
            to_location = WarehouseLocation.query.filter_by(
                id=to_location_id, warehouse_id=to_wh, company_id=company_id, status=True
            ).first()
            if not to_location:
                flash('La ubicación de destino no pertenece al almacén seleccionado.', 'danger')
                return redirect(url_for('transfer_bp.create_transfer'))

        if _same_inventory_point(from_wh, from_location_id, to_wh, to_location_id):
            flash('El origen y el destino son exactamente el mismo punto de inventario.', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))

        if not product_ids:
            flash('Debes añadir al menos un producto.', 'warning')
            return redirect(url_for('transfer_bp.create_transfer'))
        if len(product_ids) != len(quantities):
            flash('Las líneas de la transferencia están incompletas.', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))
        if len(product_ids) > 200:
            flash('Una transferencia admite como máximo 200 productos.', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))
        if user.role not in ['admin', 'superadmin'] and user.warehouse_id != from_wh:
            flash('Solo puedes transferir existencias desde tu almacén asignado.', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))

        try:
            parsed_ids = [tenant_id(raw_id, 'Producto') for raw_id in product_ids]
            unique_ids = set(parsed_ids)
            products = Product.query.options(joinedload(Product.base_uom)).filter(
                Product.company_id == company_id,
                Product.status.is_(True),
                Product.archived_at.is_(None),
                Product.id.in_(unique_ids),
            ).all()
            products_by_id = {product.id: product for product in products}
            if len(products_by_id) != len(unique_ids):
                raise BusinessRuleError('Uno de los productos seleccionados no es válido.')

            # Aggregate duplicated form rows before checking stock. This prevents
            # a forged request from reserving the same stock several times while
            # each line is validated in isolation.
            requested = {}
            for product_id, raw_quantity in zip(parsed_ids, quantities):
                product = products_by_id[product_id]
                quantity = product_quantity(
                    raw_quantity,
                    'Cantidad',
                    product=product,
                    uom=product.base_uom,
                )
                accumulated = requested.get(product_id, Decimal('0')) + quantity
                requested[product_id] = product_quantity(
                    accumulated,
                    'Cantidad total',
                    product=product,
                    uom=product.base_uom,
                )

            for product_id, quantity in requested.items():
                product = products_by_id[product_id]
                stock_from = WarehouseStock.query.filter_by(
                    product_id=product_id, warehouse_id=from_wh, company_id=company_id
                ).first()
                available = as_decimal(stock_from.quantity) if stock_from else Decimal('0')

                if from_location:
                    location_stock = LocationStock.query.filter_by(
                        location_id=from_location.id,
                        product_id=product_id,
                        company_id=company_id,
                    ).first()
                    available = as_decimal(location_stock.quantity) if location_stock else Decimal('0')
                else:
                    allocated = db.session.query(func.coalesce(func.sum(LocationStock.quantity), 0)).join(
                        WarehouseLocation, LocationStock.location_id == WarehouseLocation.id
                    ).filter(
                        WarehouseLocation.warehouse_id == from_wh,
                        WarehouseLocation.company_id == company_id,
                        LocationStock.product_id == product_id,
                        LocationStock.company_id == company_id,
                    ).scalar()
                    available -= as_decimal(allocated or 0)

                reserved_query = db.session.query(func.coalesce(func.sum(StockTransfer.quantity), 0)).filter(
                    StockTransfer.company_id == company_id,
                    StockTransfer.product_id == product_id,
                    StockTransfer.from_warehouse_id == from_wh,
                    StockTransfer.status == 'PENDING',
                )
                if from_location:
                    reserved_query = reserved_query.filter(StockTransfer.from_location_id == from_location.id)
                else:
                    reserved_query = reserved_query.filter(StockTransfer.from_location_id.is_(None))
                available -= as_decimal(reserved_query.scalar() or 0)

                if available < quantity:
                    place = from_location.full_path if from_location else origin.name
                    raise BusinessRuleError(
                        f'Stock insuficiente para {product.name} en {place}. Disponible: {available}.'
                    )

                db.session.add(StockTransfer(
                    product_id=product_id,
                    from_warehouse_id=from_wh,
                    to_warehouse_id=to_wh,
                    from_location_id=from_location.id if from_location else None,
                    to_location_id=to_location.id if to_location else None,
                    quantity=quantity,
                    company_id=company_id,
                    created_by_id=user_id,
                    status='PENDING',
                    created_at=datetime.now(),
                ))

            db.session.commit()
            flash('Orden de transferencia creada. Pendiente de recepción física.', 'success')
            return redirect(url_for('transfer_bp.transfers'))

        except BusinessRuleError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('No se pudo crear la transferencia')
            flash('No fue posible crear la transferencia. No se aplicó ningún cambio.', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))

    warehouses = Warehouse.query.filter_by(company_id=company_id, status=True).all()
    products = Product.query.options(joinedload(Product.base_uom)).filter(
        Product.company_id == company_id,
        Product.status.is_(True),
        Product.archived_at.is_(None),
        Product.product_type != ProductType.SERVICE,
    ).order_by(Product.name.asc()).all()
    locations = WarehouseLocation.query.filter_by(company_id=company_id, status=True).order_by(
        WarehouseLocation.warehouse_id.asc(), WarehouseLocation.name.asc()
    ).all()

    return render_template(
        'transfers/create.html',
        user=user,
        warehouses=warehouses,
        products=products,
        locations=locations,
    )

# ==========================================
# LISTAR TRANSFERENCIAS POR ALMACÉN (RECEPCIÓN)
# ==========================================
@transfer_bp.route('/warehouse/<int:warehouse_id>')
def transfers_by_warehouse(warehouse_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    warehouse = Warehouse.query.filter_by(id=warehouse_id, company_id=company_id).first_or_404()
    
    transfers_list = StockTransfer.query.filter_by(
        to_warehouse_id=warehouse_id,
        company_id=company_id,
        status='PENDING'
    ).order_by(StockTransfer.created_at.desc()).all()

    return render_template(
        'transfers/by_warehouse.html',
        warehouse=warehouse,
        transfers=transfers_list,
        user=user
    )

# ==========================================
# RECIBIR TRANSFERENCIA (AFECTA STOCK Y KARDEX)
# ==========================================
@transfer_bp.route('/receive/<int:transfer_id>', methods=['POST'])
def receive_transfer(transfer_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not company_id or not user_id:
        return redirect(url_for('login_bp.login'))

    transfer = StockTransfer.query.filter_by(id=transfer_id, company_id=company_id).with_for_update().first_or_404()
    user = User.query.filter_by(id=user_id, company_id=company_id).first()
    if not user or (user.role not in ['admin', 'superadmin'] and user.warehouse_id != transfer.to_warehouse_id):
        flash('Solo el almacén de destino puede confirmar esta recepción.', 'danger')
        return redirect(url_for('transfer_bp.transfers'))

    if transfer.status != 'PENDING':
        flash('Esta transferencia ya fue procesada anteriormente.', 'warning')
        return redirect(_receive_redirect_url(transfer))

    try:
        stock_from = WarehouseStock.query.filter_by(
            product_id=transfer.product_id,
            warehouse_id=transfer.from_warehouse_id,
            company_id=company_id
        ).with_for_update().first()

        if not stock_from or stock_from.quantity < transfer.quantity:
            flash('Error crítico: El almacén de origen ya no dispone del stock solicitado.', 'danger')
            return redirect(_receive_redirect_url(transfer))

        location_stock_from = None
        if transfer.from_location_id:
            location_stock_from = LocationStock.query.filter_by(
                location_id=transfer.from_location_id,
                product_id=transfer.product_id,
                company_id=company_id,
            ).with_for_update().first()
            if not location_stock_from or location_stock_from.quantity < transfer.quantity:
                flash('La ubicación de origen ya no tiene la cantidad solicitada.', 'danger')
                return redirect(_receive_redirect_url(transfer))
        else:
            allocated = db.session.query(func.coalesce(func.sum(LocationStock.quantity), 0)).join(
                WarehouseLocation, LocationStock.location_id == WarehouseLocation.id
            ).filter(
                WarehouseLocation.warehouse_id == transfer.from_warehouse_id,
                LocationStock.product_id == transfer.product_id,
                LocationStock.company_id == company_id,
            ).scalar()
            if as_decimal(stock_from.quantity) - as_decimal(allocated or 0) < as_decimal(transfer.quantity):
                flash('El stock general disponible cambió porque algunas unidades fueron asignadas a ubicaciones.', 'danger')
                return redirect(_receive_redirect_url(transfer))

        stock_to = WarehouseStock.query.filter_by(
            product_id=transfer.product_id,
            warehouse_id=transfer.to_warehouse_id,
            company_id=company_id
        ).with_for_update().first()

        if not stock_to:
            stock_to = WarehouseStock(
                product_id=transfer.product_id,
                warehouse_id=transfer.to_warehouse_id,
                company_id=company_id,
                quantity=0
            )
            db.session.add(stock_to)

        # 3. Actualizar cantidades físicas
        stock_from.quantity -= transfer.quantity
        stock_to.quantity += transfer.quantity
        if location_stock_from:
            location_stock_from.quantity -= transfer.quantity
            db.session.add(LocationMovement(
                movement_type='TRANSFER_OUT', quantity=-transfer.quantity,
                balance_after=location_stock_from.quantity, reference=f'TR{transfer.id:06d}',
                notes=f'Traslado hacia {transfer.to_location.full_path if transfer.to_location else transfer.to_warehouse.name}',
                location_id=transfer.from_location_id, product_id=transfer.product_id,
                company_id=company_id, user_id=user_id, transfer_id=transfer.id,
            ))
        if transfer.to_location_id:
            location_stock_to = LocationStock.query.filter_by(
                location_id=transfer.to_location_id,
                product_id=transfer.product_id,
                company_id=company_id,
            ).with_for_update().first()
            if not location_stock_to:
                location_stock_to = LocationStock(
                    location_id=transfer.to_location_id,
                    product_id=transfer.product_id,
                    company_id=company_id,
                    quantity=0,
                )
                db.session.add(location_stock_to)
            location_stock_to.quantity += transfer.quantity
            db.session.add(LocationMovement(
                movement_type='TRANSFER_IN', quantity=transfer.quantity,
                balance_after=location_stock_to.quantity, reference=f'TR{transfer.id:06d}',
                notes=f'Recepción desde {transfer.from_location.full_path if transfer.from_location else transfer.from_warehouse.name}',
                location_id=transfer.to_location_id, product_id=transfer.product_id,
                company_id=company_id, user_id=user_id, transfer_id=transfer.id,
            ))

        # 4. Registrar movimientos en Kardex para auditoría
        db.session.add(StockMovement(
            product_id=transfer.product_id,
            warehouse_id=transfer.from_warehouse_id,
            company_id=company_id,
            user_id=user_id,
            movement_type='OUT',
            quantity=transfer.quantity,
            reason=f'Transferencia enviada #{transfer.id}' + (
                f' · {transfer.from_location.full_path}' if transfer.from_location else ''
            )
        ))
        
        db.session.add(StockMovement(
            product_id=transfer.product_id,
            warehouse_id=transfer.to_warehouse_id,
            company_id=company_id,
            user_id=user_id,
            movement_type='IN',
            quantity=transfer.quantity,
            reason=f'Transferencia recibida #{transfer.id}' + (
                f' · {transfer.to_location.full_path}' if transfer.to_location else ''
            )
        ))

        # 5. Marcar como finalizada
        transfer.status = 'RECEIVED'
        transfer.received_by_id = user_id

        db.session.commit()
        if transfer.from_warehouse_id == transfer.to_warehouse_id:
            flash('Movimiento interno confirmado. Stock reasignado entre ubicaciones.', 'success')
        else:
            flash('Recepción confirmada. Inventario actualizado en ambos almacenes.', 'success')
    
    except Exception:
        db.session.rollback()
        current_app.logger.exception('No se pudo recibir la transferencia %s', transfer_id)
        flash('No fue posible recibir la transferencia. No se aplicó ningún cambio.', 'danger')

    return redirect(_receive_redirect_url(transfer))

# ==========================================
# VISTA DETALLADA DE TRANSFERENCIA
# ==========================================
@transfer_bp.route('/view/<int:transfer_id>')
def view_transfer(transfer_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    transfer = StockTransfer.query.filter_by(id=transfer_id, company_id=company_id).first_or_404()

    return render_template(
        'transfers/view_detail.html',
        transfer=transfer,
        user=user
    )
    
@transfer_bp.route('/print/<int:transfer_id>')
def print_transfer(transfer_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not company_id or not user_id:
        return redirect(url_for('login_bp.login'))

    transfer = StockTransfer.query.options(
        joinedload(StockTransfer.product),
        joinedload(StockTransfer.from_warehouse),
        joinedload(StockTransfer.to_warehouse),
        joinedload(StockTransfer.from_location),
        joinedload(StockTransfer.to_location),
        joinedload(StockTransfer.creator),
    ).filter_by(id=transfer_id, company_id=company_id).first_or_404()
    user = User.query.filter_by(id=user_id, company_id=company_id).first()

    pdf = build_transfer_pdf(transfer=transfer, user=user)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=Conduce_TR{transfer.id}.pdf'
    return response

@transfer_bp.route('/api/get_details/<string:code>')
def api_get_transfer(code):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not company_id or not user_id:
        return jsonify({"success": False, "message": "Autenticacion requerida"}), 401

    match = re.fullmatch(r'(?:TR)?([0-9]{1,18})', (code or '').strip(), flags=re.IGNORECASE)
    if not match:
        return jsonify({"success": False, "message": "Codigo de conduce invalido"}), 400

    try:
        user = User.query.filter_by(id=user_id, company_id=company_id).first()
        if not user:
            return jsonify({"success": False, "message": "Sesion no valida"}), 401

        transfer_id = int(match.group(1))
        transfer = StockTransfer.query.options(
            joinedload(StockTransfer.product).joinedload(Product.base_uom),
            joinedload(StockTransfer.from_warehouse),
            joinedload(StockTransfer.to_warehouse),
            joinedload(StockTransfer.from_location),
            joinedload(StockTransfer.to_location),
        ).filter_by(id=transfer_id, company_id=company_id).first()

        if not transfer:
            return jsonify({"success": False, "message": "Transferencia no encontrada"}), 404
        if transfer.status == 'RECEIVED':
            return jsonify({"success": False, "message": "Esta transferencia ya fue recibida"}), 409
        if transfer.status == 'CANCELLED':
            return jsonify({"success": False, "message": "Esta transferencia fue cancelada"}), 409
        if transfer.status != 'PENDING':
            return jsonify({"success": False, "message": "La transferencia no esta disponible"}), 409
        if user.role not in ['admin', 'superadmin'] and user.warehouse_id != transfer.to_warehouse_id:
            return jsonify({"success": False, "message": "Solo el almacen de destino puede escanear este traslado"}), 403
        if transfer.product.tracking in {'LOT', 'SERIAL'}:
            return jsonify({
                "success": False,
                "message": "Este producto requiere trazabilidad por lote o serie y no puede recibirse en el flujo generico.",
            }), 409

        product = transfer.product
        barcodes = ProductBarcode.query.filter_by(
            company_id=company_id,
            product_id=product.id,
        ).order_by(ProductBarcode.is_primary.desc(), ProductBarcode.id.asc()).all()
        scan_codes = [product.sku, str(product.id)] + [row.code for row in barcodes]
        scan_codes = [value for value in dict.fromkeys(scan_codes) if value]
        fractional = bool(
            product.sale_mode == 'WEIGHT'
            or (product.base_uom is not None and bool(product.base_uom.allow_fraction))
        )
        uom = (
            product.base_uom.symbol
            if product.base_uom is not None and product.base_uom.symbol
            else ('kg' if product.sale_mode == 'WEIGHT' else 'ud')
        )

        response = jsonify({
            "success": True,
            "transfer": {
                "id": transfer.id,
                "ref_code": f"TR{transfer.id:06d}",
                "origin": transfer.from_warehouse.name,
                "destination": transfer.to_warehouse.name,
                "origin_location": transfer.from_location.full_path if transfer.from_location else None,
                "destination_location": transfer.to_location.full_path if transfer.to_location else None,
                "destination_location_barcode": transfer.to_location.barcode if transfer.to_location else None,
                "product_name": product.name,
                "product_sku": product.sku or "S/SKU",
                "product_id": product.id,
                "expected_qty": display_quantity(transfer.quantity),
                "fractional": fractional,
                "uom": uom,
                "tracking": product.tracking,
                "scan_codes": scan_codes,
            },
        })
        response.headers['Cache-Control'] = 'no-store, private'
        return response
    except Exception:
        current_app.logger.exception('No se pudo consultar la transferencia %s', match.group(1))
        return jsonify({"success": False, "message": "No se pudo consultar la transferencia"}), 500

@transfer_bp.route('/scanner-mode')
def scanner_mode():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))
    user = User.query.filter_by(id=user_id, company_id=company_id).first()
    if not user:
        session.clear()
        return redirect(url_for('login_bp.login'))
    return render_template('transfers/scanner_validation.html', user=user)


@transfer_bp.route('/api/locations')
def api_locations():
    company_id = session.get('company_id')
    warehouse_id = request.args.get('warehouse_id', type=int)
    if not company_id or not warehouse_id:
        return jsonify({'success': False, 'locations': []}), 400
    locations = WarehouseLocation.query.filter_by(
        warehouse_id=warehouse_id,
        company_id=company_id,
        status=True,
    ).order_by(WarehouseLocation.name.asc()).all()
    return jsonify({
        'success': True,
        'locations': [
            {'id': row.id, 'name': row.name, 'path': row.full_path, 'barcode': row.barcode}
            for row in locations
        ],
    })


@transfer_bp.route('/api/location/<path:code>')
def api_location_by_barcode(code):
    company_id = session.get('company_id')
    clean_code = (code or '').strip().upper()
    location = WarehouseLocation.query.filter_by(
        barcode=clean_code,
        company_id=company_id,
        status=True,
    ).first()
    if not location:
        return jsonify({'success': False, 'message': 'Ubicación no encontrada'}), 404
    return jsonify({
        'success': True,
        'location': {
            'id': location.id,
            'name': location.name,
            'path': location.full_path,
            'barcode': location.barcode,
            'warehouse_id': location.warehouse_id,
            'warehouse_name': location.warehouse.name,
        },
    })

