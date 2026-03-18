from flask import request, session, flash, redirect, url_for, current_app
from db import db
from models.sales.sales import Sale
from models.company.company import Company
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.stock_movement.stock_movement import StockMovement
from datetime import datetime, timezone
from decimal import Decimal
from .core import recalc_sale 

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

    company = db.session.get(Company, company_id)
    if not company:
        flash('Error de consistencia de empresa', 'danger')
        return redirect(url_for('login_bp.login'))

    # Validación de límites del plan
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
        sale.status = 'PENDING' 
    else:
        sale.payment_method = 'CASH'
        sale.amount_paid = sale.total
        sale.balance = Decimal('0.00')
        sale.status = 'COMPLETED'
        
    # Procesamiento de Inventario
    for item in sale.items:
        stock = WarehouseStock.query.filter_by(
            product_id=item.product_id, 
            warehouse_id=item.warehouse_id
        ).first()
        
        if not stock or stock.quantity < item.quantity:
            flash(f'Stock insuficiente para {item.product.name}', 'danger')
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
            created_at=datetime.now(timezone.utc) 
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

# =========================
# CANCELAR VENTA
# =========================
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

# =========================
# CONVERTIR EN COTIZACIÓN
# =========================
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
    db.session.commit()
    session.pop('current_sale_id', None)
    
    flash(f'Venta #{sale.id} guardada como Cotización', 'success')
    return redirect(url_for('sales_bp.list_sales'))