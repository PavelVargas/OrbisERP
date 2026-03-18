from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from decimal import Decimal
from models.supplier.supplier import Supplier
from models.purchase.purchase_order import PurchaseOrder
from models.user.user import User # Importamos el modelo User
from db import db

supplier_bp = Blueprint('supplier_bp', __name__, url_prefix='/suppliers')

# =========================
# LISTA
# =========================
@supplier_bp.route('/')
def supplier_list():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id) # Carga del usuario para la barra lateral

    # Filtrar estrictamente por empresa
    suppliers = Supplier.query.filter_by(company_id=company_id).order_by(Supplier.name.asc()).all()
    
    return render_template(
        'suppliers/list.html',
        suppliers=suppliers,
        user=user # Pasamos user a la plantilla
    )


# =========================
# CREAR
# =========================
@supplier_bp.route('/create', methods=['GET', 'POST'])
def supplier_create():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    if request.method == 'POST':
        supplier = Supplier(
            name=request.form['name'],
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            company_id=company_id
        )

        db.session.add(supplier)
        db.session.commit()

        flash(f'Proveedor "{supplier.name}" creado correctamente', 'success')
        return redirect(url_for('supplier_bp.supplier_list'))

    user = User.query.get(user_id)
    return render_template('suppliers/create.html', user=user)


# =========================
# EDITAR
# =========================
@supplier_bp.route('/edit/<int:supplier_id>', methods=['GET', 'POST'])
def supplier_edit(supplier_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    # Seguridad: Solo obtener si pertenece a la empresa
    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).first_or_404()

    if request.method == 'POST':
        supplier.name = request.form['name']
        supplier.email = request.form.get('email')
        supplier.phone = request.form.get('phone')

        db.session.commit()
        flash('Proveedor actualizado correctamente', 'success')
        return redirect(url_for('supplier_bp.supplier_list'))

    user = User.query.get(user_id)
    return render_template(
        'suppliers/edit.html',
        supplier=supplier,
        user=user
    )


# =========================
# ELIMINAR
# =========================
@supplier_bp.route('/delete/<int:supplier_id>', methods=['POST'])
def supplier_delete(supplier_id):
    company_id = session.get('company_id')
    if not company_id:
        return redirect(url_for('login_bp.login'))

    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).first_or_404()

    db.session.delete(supplier)
    db.session.commit()

    flash('Proveedor eliminado permanentemente', 'info')
    return redirect(url_for('supplier_bp.supplier_list'))


# =========================
# HISTORIAL DE COMPRAS
# =========================
@supplier_bp.route('/<int:supplier_id>/history')
def supplier_purchase_history(supplier_id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    # Validar que el proveedor pertenezca a la empresa
    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).first_or_404()

    # Filtrar órdenes de compra por proveedor Y empresa
    orders = PurchaseOrder.query.filter_by(
        supplier_id=supplier_id,
        company_id=company_id
    ).order_by(
        PurchaseOrder.created_at.desc()
    ).all()

    total_spent = sum(
        (o.total_cost or Decimal('0.00'))
        for o in orders
    )

    user = User.query.get(user_id)
    return render_template(
        'suppliers/supplier_history.html',
        supplier=supplier,
        orders=orders,
        total_spent=total_spent,
        user=user
    )