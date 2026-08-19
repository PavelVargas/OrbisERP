from flask import request, session, flash, redirect, url_for, current_app
from db import db
from models.sales.sales import Sale
from models.company.company import Company
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.warehouse_location.warehouse_location import LocationStock, WarehouseLocation
from models.stock_movement.stock_movement import StockMovement
from models.stock_transfer.stock_transfer import StockTransfer
from datetime import datetime
from decimal import Decimal
from .core import recalc_sale 
from sqlalchemy import func

from .sales import sales_bp

# ==========================================================
# FINALIZAR VENTA (CRÉDITO, EFECTIVO Y LÓGICA DE STOCK)
# ==========================================================
@sales_bp.route('/finish', methods=['POST'])
def finish_sale():
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    user_id = session.get('user_id')

    if not company_id or not sale_id:
        flash('Sesión de venta no encontrada', 'danger')
        return redirect(url_for('sales_bp.create_sale'))

    company = Company.query.filter_by(id=company_id).with_for_update().first()
    if not company:
        flash('Error de consistencia de empresa', 'danger')
        return redirect(url_for('login_bp.login'))

    limits = company.get_plan_limits()
    current_usage = company.get_current_month_usage()

    if current_usage >= limits['max_monthly_invoices']:
        flash(f'Límite de facturación alcanzado ({limits["max_monthly_invoices"]} facturas/mes). ' 
              f'Tu plan actual es {company.plan_name}. Por favor, solicita un upgrade.', 'warning')
        return redirect(url_for('sales_bp.create_sale'))

    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()

    if sale.user_id != user_id:
        flash('No tienes permiso para finalizar esta venta', 'danger')
        return redirect(url_for('sales_bp.list_sales'))

    if not sale.items:
        flash('La venta no tiene productos', 'warning')
        return redirect(url_for('sales_bp.create_sale'))

    if not sale.client_id:
        flash('Debes asignar un cliente antes de finalizar', 'warning')
        return redirect(url_for('sales_bp.create_sale'))

    payment_method = request.form.get('payment_method', 'CASH')
    
    recalc_sale(sale)

    if payment_method == 'CREDIT':
        sale.payment_method = 'CREDIT'
        sale.amount_paid = Decimal('0.00')
        sale.balance = sale.total  
    else:
        sale.payment_method = 'CASH'
        sale.amount_paid = sale.total
        sale.balance = Decimal('0.00')
        
    sale.status = 'COMPLETED'
    sale.created_at = datetime.now() 

    for item in sale.items:
        p_type = str(item.product.product_type.value if hasattr(item.product.product_type, 'value') else item.product.product_type).upper()
        is_service = p_type in ['SERVICE', 'SERVICIO']

        if is_service:
            continue

        stock = WarehouseStock.query.filter_by(
            product_id=item.product_id, 
            warehouse_id=item.warehouse_id,
            company_id=company_id,
        ).with_for_update().first()
        
        if not stock or stock.quantity < item.quantity:
            flash(f'Stock insuficiente para {item.product.name}', 'danger')
            db.session.rollback() 
            return redirect(url_for('sales_bp.create_sale'))
        reserved = db.session.query(func.coalesce(func.sum(StockTransfer.quantity), 0)).filter(
            StockTransfer.product_id == item.product_id,
            StockTransfer.from_warehouse_id == item.warehouse_id,
            StockTransfer.company_id == company_id,
            StockTransfer.status == 'PENDING',
        ).scalar()
        if int(stock.quantity or 0) - int(reserved or 0) < item.quantity:
            flash(f'Parte del stock de {item.product.name} está reservado en traslados pendientes.', 'danger')
            db.session.rollback()
            return redirect(url_for('sales_bp.create_sale'))
        
        location_rows = LocationStock.query.join(WarehouseLocation).filter(
            WarehouseLocation.warehouse_id == item.warehouse_id,
            LocationStock.product_id == item.product_id,
            LocationStock.company_id == company_id,
            LocationStock.quantity > 0,
        ).order_by(LocationStock.location_id.asc()).with_for_update().all()
        allocated = sum(int(row.quantity or 0) for row in location_rows)
        unassigned = max(int(stock.quantity or 0) - allocated, 0)
        remaining_from_locations = max(int(item.quantity) - unassigned, 0)
        for location_row in location_rows:
            if remaining_from_locations <= 0:
                break
            taken = min(int(location_row.quantity or 0), remaining_from_locations)
            location_row.quantity -= taken
            remaining_from_locations -= taken
        if remaining_from_locations > 0:
            flash(f'La distribución física de {item.product.name} no coincide con el stock del almacén.', 'danger')
            db.session.rollback()
            return redirect(url_for('sales_bp.create_sale'))

        stock.quantity -= item.quantity

        movement = StockMovement(
            product_id=item.product_id,
            warehouse_id=item.warehouse_id,
            company_id=company_id,
            movement_type='OUT',
            quantity=item.quantity,
            reason=f'Venta #{sale.id}',
            created_at=datetime.now()
        )
        db.session.add(movement)
    
    try:
        db.session.commit()
        session.pop('current_sale_id', None)
        
        flash(f'Venta #{sale.id} finalizada exitosamente', 'success')
        return redirect(url_for('sales_bp.list_sales'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error al finalizar venta: {str(e)}")
        flash(f'Error crítico: {str(e)}', 'danger')
        return redirect(url_for('sales_bp.create_sale'))

# ==========================================================
# CANCELAR VENTA
# ==========================================================
@sales_bp.route('/cancel/<int:sale_id>', methods=['POST'])
def cancel_sale(sale_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()

    if sale.user_id != user_id:
        flash('No tienes permisos para cancelar esta venta', 'danger')
        return redirect(url_for('sales_bp.list_sales'))

    if sale.status not in ['PENDING', 'QUOTATION']:
        flash('No se pueden cancelar ventas finalizadas', 'warning')
        return redirect(url_for('sales_bp.list_sales'))

    sale.status = 'CANCELLED'
    
    if session.get('current_sale_id') == sale.id:
        session.pop('current_sale_id', None)

    db.session.commit()
    flash(f'Venta #{sale.id} cancelada', 'info')
    return redirect(url_for('sales_bp.list_sales'))

# ==========================================================
# CONVERTIR EN COTIZACIÓN (MANTENIENDO RELACIONES DE OBJETOS)
# ==========================================================
@sales_bp.route('/quote/<int:sale_id>', methods=['POST'])
def convert_to_quote(sale_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()

    if sale.user_id != user_id:
        flash('No tienes permiso para realizar esta acción', 'danger')
        return redirect(url_for('sales_bp.list_sales'))

    if not sale.items:
        flash('No puedes cotizar una venta sin productos', 'warning')
        return redirect(url_for('sales_bp.create_sale'))
    
    sale.status = 'QUOTATION'
    
    # Recalculamos totales antes de asentar el estado intermedio
    recalc_sale(sale)
    
    try:
        db.session.commit()
        # Remover de la sesión activa de creación de manera segura
        if session.get('current_sale_id') == sale.id:
            session.pop('current_sale_id', None)
        
        flash(f'Venta #{sale.id} guardada como Cotización con {len(sale.items)} ítems vinculados', 'success')
        return redirect(url_for('sales_bp.list_sales'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar cotización: {str(e)}', 'danger')
        return redirect(url_for('sales_bp.create_sale'))
