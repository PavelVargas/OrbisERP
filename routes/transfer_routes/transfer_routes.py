from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models.stock_transfer.stock_transfer import StockTransfer
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.warehouse_location.warehouse_location import LocationMovement, LocationStock, WarehouseLocation
from models.products.products import Product, ProductType
from models.stock_movement.stock_movement import StockMovement
from models.user.user import User
from db import db
from datetime import datetime
import pdfkit
import base64
import io
from barcode import Code128
from barcode.writer import ImageWriter
from flask import render_template, make_response
import re
from sqlalchemy import func

transfer_bp = Blueprint('transfer_bp', __name__, url_prefix='/transfers')

def _same_inventory_point(from_warehouse_id, from_location_id, to_warehouse_id, to_location_id):
    """General stock and every nested location are separate inventory nodes."""
    return from_warehouse_id == to_warehouse_id and from_location_id == to_location_id

# ==========================================
# LISTAR TODAS LAS TRANSFERENCIAS
# ==========================================
@transfer_bp.route('/')
def transfers():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    products = Product.query.filter_by(company_id=company_id, status=True).all()
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

    user = User.query.get(user_id)

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
            flash('Debes añadir al menos un producto', 'warning')
            return redirect(url_for('transfer_bp.create_transfer'))
        if len(product_ids) != len(quantities):
            flash('Las líneas de la transferencia están incompletas.', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))
        if user.role not in ['admin', 'superadmin'] and user.warehouse_id != from_wh:
            flash('Solo puedes transferir existencias desde tu almacén asignado.', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))

        try:
            for p_id, qty in zip(product_ids, quantities):
                p_id = int(p_id)
                qty = int(qty)
                if qty <= 0:
                    raise ValueError('Las cantidades deben ser números enteros mayores que cero.')

                stock_from = WarehouseStock.query.filter_by(
                    product_id=p_id, warehouse_id=from_wh, company_id=company_id
                ).first()

                product_obj = Product.query.filter_by(id=p_id, company_id=company_id, status=True).first()
                if not product_obj:
                    raise ValueError('Uno de los productos seleccionados no es válido.')
                available = int(stock_from.quantity or 0) if stock_from else 0
                if from_location:
                    location_stock = LocationStock.query.filter_by(
                        location_id=from_location.id, product_id=p_id, company_id=company_id
                    ).first()
                    available = int(location_stock.quantity or 0) if location_stock else 0
                else:
                    allocated = db.session.query(func.coalesce(func.sum(LocationStock.quantity), 0)).join(
                        WarehouseLocation, LocationStock.location_id == WarehouseLocation.id
                    ).filter(
                        WarehouseLocation.warehouse_id == from_wh,
                        LocationStock.product_id == p_id,
                        LocationStock.company_id == company_id,
                    ).scalar()
                    available -= int(allocated or 0)
                reserved_query = db.session.query(func.coalesce(func.sum(StockTransfer.quantity), 0)).filter(
                    StockTransfer.company_id == company_id,
                    StockTransfer.product_id == p_id,
                    StockTransfer.from_warehouse_id == from_wh,
                    StockTransfer.status == 'PENDING',
                )
                if from_location:
                    reserved_query = reserved_query.filter(StockTransfer.from_location_id == from_location.id)
                else:
                    reserved_query = reserved_query.filter(StockTransfer.from_location_id.is_(None))
                available -= int(reserved_query.scalar() or 0)
                if available < qty:
                    place = from_location.full_path if from_location else origin.name
                    raise ValueError(f'Stock insuficiente para {product_obj.name} en {place}. Disponible: {available}.')

                transfer = StockTransfer(
                    product_id=p_id,
                    from_warehouse_id=from_wh,
                    to_warehouse_id=to_wh,
                    from_location_id=from_location.id if from_location else None,
                    to_location_id=to_location.id if to_location else None,
                    quantity=qty,
                    company_id=company_id,
                    status='PENDING',
                    created_at=datetime.now()
                )
                db.session.add(transfer)
            
            db.session.commit()
            flash('Orden de transferencia creada. Pendiente de recepción física.', 'success')
            return redirect(url_for('transfer_bp.transfers'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar: {str(e)}', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))

    warehouses = Warehouse.query.filter_by(company_id=company_id, status=True).all()
    products = Product.query.filter_by(company_id=company_id, status=True).filter(
        Product.product_type != ProductType.SERVICE
    ).all()
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
    if not company_id:
        return redirect(url_for('login_bp.login'))

    transfer = StockTransfer.query.filter_by(id=transfer_id, company_id=company_id).with_for_update().first_or_404()
    user = db.session.get(User, user_id) if user_id else None
    if not user or (user.role not in ['admin', 'superadmin'] and user.warehouse_id != transfer.to_warehouse_id):
        flash('Solo el almacén de destino puede confirmar esta recepción.', 'danger')
        return redirect(url_for('transfer_bp.transfers'))

    if transfer.status != 'PENDING':
        flash('Esta transferencia ya fue procesada anteriormente.', 'warning')
        return redirect(request.referrer)

    try:
        stock_from = WarehouseStock.query.filter_by(
            product_id=transfer.product_id,
            warehouse_id=transfer.from_warehouse_id,
            company_id=company_id
        ).with_for_update().first()

        if not stock_from or stock_from.quantity < transfer.quantity:
            flash('Error crítico: El almacén de origen ya no dispone del stock solicitado.', 'danger')
            return redirect(request.referrer)

        location_stock_from = None
        if transfer.from_location_id:
            location_stock_from = LocationStock.query.filter_by(
                location_id=transfer.from_location_id,
                product_id=transfer.product_id,
                company_id=company_id,
            ).with_for_update().first()
            if not location_stock_from or location_stock_from.quantity < transfer.quantity:
                flash('La ubicación de origen ya no tiene la cantidad solicitada.', 'danger')
                return redirect(request.referrer)
        else:
            allocated = db.session.query(func.coalesce(func.sum(LocationStock.quantity), 0)).join(
                WarehouseLocation, LocationStock.location_id == WarehouseLocation.id
            ).filter(
                WarehouseLocation.warehouse_id == transfer.from_warehouse_id,
                LocationStock.product_id == transfer.product_id,
                LocationStock.company_id == company_id,
            ).scalar()
            if int(stock_from.quantity or 0) - int(allocated or 0) < transfer.quantity:
                flash('El stock general disponible cambió porque algunas unidades fueron asignadas a ubicaciones.', 'danger')
                return redirect(request.referrer)

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
            movement_type='IN',
            quantity=transfer.quantity,
            reason=f'Transferencia recibida #{transfer.id}' + (
                f' · {transfer.to_location.full_path}' if transfer.to_location else ''
            )
        ))

        # 5. Marcar como finalizada
        transfer.status = 'RECEIVED'

        db.session.commit()
        if transfer.from_warehouse_id == transfer.to_warehouse_id:
            flash('Movimiento interno confirmado. Stock reasignado entre ubicaciones.', 'success')
        else:
            flash('Recepción confirmada. Inventario actualizado en ambos almacenes.', 'success')
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error en el proceso de recepción: {str(e)}', 'danger')

    return redirect(request.referrer)

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
    transfer = StockTransfer.query.filter_by(id=transfer_id, company_id=company_id).first_or_404()

    barcode_value = f"TR{transfer.id:06d}" 
    
    buffer = io.BytesIO()
    Code128(barcode_value, writer=ImageWriter()).write(buffer)
    barcode_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    html_content = render_template(
        'transfers/pdf_template.html', 
        transfer=transfer, 
        barcode_base64=barcode_base64
    )

    options = {
        'page-size': 'A4',
        'margin-top': '0mm',
        'margin-right': '0mm',
        'margin-bottom': '0mm',
        'margin-left': '0mm',
        'encoding': "UTF-8",
        'enable-local-file-access': None
    }
    
    pdf = pdfkit.from_string(html_content, False, options=options)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=Conduce_TR{transfer.id}.pdf'
    
    return response

@transfer_bp.route('/api/get_details/<string:code>')
def api_get_transfer(code):
    company_id = session.get('company_id')
    try:
        numeric_id = re.sub(r'[^0-9]', '', code)
        
        if not numeric_id:
            return {"success": False, "message": "Código inválido"}, 400

        t = StockTransfer.query.filter_by(id=int(numeric_id), company_id=company_id).first()

        if not t:
            return {"success": False, "message": "Transferencia no encontrada"}, 404
        
        if t.status != 'PENDING':
            return {"success": False, "message": "Esta transferencia ya fue recibida"}, 400

        return {
            "success": True,
            "transfer": {
                "id": t.id,
                "ref_code": f"TR{t.id:06d}",
                "origin": t.from_warehouse.name,
                "destination": t.to_warehouse.name,
                "origin_location": t.from_location.full_path if t.from_location else None,
                "destination_location": t.to_location.full_path if t.to_location else None,
                "destination_location_barcode": t.to_location.barcode if t.to_location else None,
                "product_name": t.product.name,
                "product_sku": t.product.sku or "S/SKU",
                "product_id": t.product.id,
                "expected_qty": t.quantity
            }
        }
    except Exception as e:
        return {"success": False, "message": str(e)}, 400

@transfer_bp.route('/scanner-mode')
def scanner_mode():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))
    user = db.session.get(User, user_id)
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

