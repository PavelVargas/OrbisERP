from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import db
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.user.user import User

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
    if user.role not in ['admin', 'superadmin']:
        flash('Acceso denegado: Solo administradores', 'danger')
        return redirect(url_for('warehouse_bp.list_warehouses'))

    if request.method == 'POST':
        # 3. VALIDACIÓN DE LÍMITE DE PLAN (El Superadmin ignora esta restricción si quieres)
        if user.role == 'admin':
            if current_wares_count >= plan_limits['max_warehouses']:
                flash(f"Límite alcanzado para el plan {plan_name}. Máximo: {plan_limits['max_warehouses']}.", 'warning')
                return redirect(url_for('warehouse_bp.list_warehouses'))

        name = request.form['name']
        location = request.form.get('location')

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
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear almacén: {str(e)}', 'danger')

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
    
    if user.role not in ['admin', 'superadmin']:
        flash('Acceso denegado', 'danger')
        return redirect(url_for('warehouse_bp.list_warehouses'))

    # Seguridad: El almacén debe pertenecer a la empresa activa en la sesión
    warehouse = Warehouse.query.filter_by(id=id, company_id=company_id).first_or_404()
    
    if request.method == 'POST':
        warehouse.name = request.form['name']
        warehouse.location = request.form.get('location')
        try:
            db.session.commit()
            flash('Almacén actualizado correctamente', 'success')
            return redirect(url_for('warehouse_bp.list_warehouses'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')
        
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
    stocks = WarehouseStock.query.filter_by(warehouse_id=id).all()
    
    return render_template('warehouse/stock.html', warehouse=warehouse, stocks=stocks, user=user)