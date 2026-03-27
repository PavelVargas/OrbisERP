from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models.stock_transfer.stock_transfer import StockTransfer
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.products.products import Product
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

transfer_bp = Blueprint('transfer_bp', __name__, url_prefix='/transfers')

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
    transfers_list = StockTransfer.query.filter_by(company_id=company_id).order_by(StockTransfer.created_at.desc()).all()

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
        from_wh = int(request.form['from_warehouse'])
        to_wh = int(request.form['to_warehouse'])
        product_ids = request.form.getlist('product_ids[]')
        quantities = request.form.getlist('quantities[]')

        if from_wh == to_wh:
            flash('No puedes transferir al mismo almacén', 'danger')
            return redirect(url_for('transfer_bp.create_transfer'))

        if not product_ids:
            flash('Debes añadir al menos un producto', 'warning')
            return redirect(url_for('transfer_bp.create_transfer'))

        try:
            for p_id, qty in zip(product_ids, quantities):
                p_id = int(p_id)
                qty = float(qty)

                stock_from = WarehouseStock.query.filter_by(
                    product_id=p_id, warehouse_id=from_wh, company_id=company_id
                ).first()

                if not stock_from or stock_from.quantity < qty:
                    product_obj = Product.query.get(p_id)
                    flash(f'Atención: Stock insuficiente en origen para {product_obj.name}. Verifique antes de enviar.', 'warning')

                transfer = StockTransfer(
                    product_id=p_id,
                    from_warehouse_id=from_wh,
                    to_warehouse_id=to_wh,
                    quantity=qty,
                    company_id=company_id,
                    status='PENDING',
                    created_at=datetime.utcnow()
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
    products = Product.query.filter_by(company_id=company_id, status=True).all()
    
    return render_template(
        'transfers/create.html', 
        user=user, 
        warehouses=warehouses, 
        products=products 
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
    if not company_id:
        return redirect(url_for('login_bp.login'))

    transfer = StockTransfer.query.filter_by(id=transfer_id, company_id=company_id).first_or_404()

    if transfer.status != 'PENDING':
        flash('Esta transferencia ya fue procesada anteriormente.', 'warning')
        return redirect(request.referrer)

    try:
        stock_from = WarehouseStock.query.filter_by(
            product_id=transfer.product_id,
            warehouse_id=transfer.from_warehouse_id,
            company_id=company_id
        ).first()

        if not stock_from or stock_from.quantity < transfer.quantity:
            flash('Error crítico: El almacén de origen ya no dispone del stock solicitado.', 'danger')
            return redirect(request.referrer)

        stock_to = WarehouseStock.query.filter_by(
            product_id=transfer.product_id,
            warehouse_id=transfer.to_warehouse_id,
            company_id=company_id
        ).first()

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

        # 4. Registrar movimientos en Kardex para auditoría
        db.session.add(StockMovement(
            product_id=transfer.product_id,
            warehouse_id=transfer.from_warehouse_id,
            company_id=company_id,
            movement_type='OUT',
            quantity=transfer.quantity,
            reason=f'Transferencia enviada #{transfer.id}'
        ))
        
        db.session.add(StockMovement(
            product_id=transfer.product_id,
            warehouse_id=transfer.to_warehouse_id,
            company_id=company_id,
            movement_type='IN',
            quantity=transfer.quantity,
            reason=f'Transferencia recibida #{transfer.id}'
        ))

        # 5. Marcar como finalizada
        transfer.status = 'RECEIVED'

        db.session.commit()
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
    user = User.query.get(user_id)
    return render_template('transfers/scanner_validation.html', user=user)

