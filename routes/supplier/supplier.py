from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
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

@supplier_bp.route('/api/create', methods=['POST'])
def supplier_create_api():
    company_id = session.get('company_id')
    if not session.get('user_id') or not company_id:
        return jsonify({'error': 'Autenticación requerida'}), 401
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip() or None
    phone = (data.get('phone') or '').strip() or None
    if len(name) < 2 or len(name) > 150:
        return jsonify({'error': 'Escribe un nombre de 2 a 150 caracteres.'}), 400
    if email and ('@' not in email or len(email) > 120):
        return jsonify({'error': 'El correo no es válido.'}), 400
    existing = Supplier.query.filter(
        Supplier.company_id == company_id,
        db.func.lower(Supplier.name) == name.lower(),
    ).first()
    if existing:
        return jsonify({'id': existing.id, 'name': existing.name, 'existing': True})
    supplier = Supplier(name=name, email=email, phone=phone, company_id=company_id)
    db.session.add(supplier)
    db.session.commit()
    return jsonify({'id': supplier.id, 'name': supplier.name, 'existing': False}), 201


@supplier_bp.route('/api/<int:supplier_id>', methods=['PATCH'])
def supplier_update_api(supplier_id):
    company_id = session.get('company_id')
    if not session.get('user_id') or not company_id:
        return jsonify({'error': 'Autenticación requerida'}), 401
    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).first_or_404()
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip() or None
    phone = (data.get('phone') or '').strip() or None
    if len(name) < 2 or len(name) > 150:
        return jsonify({'error': 'Escribe un nombre de 2 a 150 caracteres.'}), 400
    if email and ('@' not in email or len(email) > 120):
        return jsonify({'error': 'El correo no es válido.'}), 400
    duplicate = Supplier.query.filter(
        Supplier.company_id == company_id,
        Supplier.id != supplier.id,
        db.func.lower(Supplier.name) == name.lower(),
    ).first()
    if duplicate:
        return jsonify({'error': 'Ya existe otro proveedor con ese nombre.'}), 409
    supplier.name, supplier.email, supplier.phone = name, email, phone
    db.session.commit()
    return jsonify({'id': supplier.id, 'name': supplier.name, 'email': supplier.email, 'phone': supplier.phone})


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
