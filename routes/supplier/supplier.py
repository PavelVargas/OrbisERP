from services.time_utils import utcnow
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from decimal import Decimal
from models.supplier.supplier import Supplier
from models.purchase.purchase_order import PurchaseOrder
from models.backoffice import SupplierBill, SupplierPayment
from models.productivity import CompanyDocument
from models.user.user import User # Importamos el modelo User
from db import db
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

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
    suppliers = Supplier.query.filter_by(company_id=company_id).filter(Supplier.archived_at.is_(None)).order_by(Supplier.name.asc()).all()
    aggregates = db.session.query(
        PurchaseOrder.supplier_id,
        func.count(PurchaseOrder.id),
        func.coalesce(func.sum(PurchaseOrder.total_cost), 0),
        func.max(PurchaseOrder.created_at),
    ).filter(PurchaseOrder.company_id == company_id).group_by(PurchaseOrder.supplier_id).all()
    supplier_stats = {supplier_id: {'orders': int(count or 0), 'spent': total or Decimal('0'), 'last_order': last_order}
                      for supplier_id, count, total, last_order in aggregates}
    total_orders = sum(row['orders'] for row in supplier_stats.values())
    total_spent = sum((Decimal(row['spent'] or 0) for row in supplier_stats.values()), Decimal('0'))
    
    return render_template(
        'suppliers/list.html',
        suppliers=suppliers,
        user=user,
        supplier_stats=supplier_stats,
        total_orders=total_orders,
        total_spent=total_spent,
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
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower() or None
        phone = (request.form.get('phone') or '').strip() or None
        if len(name) < 2:
            flash('El nombre debe tener al menos 2 caracteres.', 'danger')
            return redirect(request.url)
        if email and ('@' not in email or len(email) > 120):
            flash('Escribe un correo válido.', 'danger')
            return redirect(request.url)
        supplier = Supplier(
            name=name[:150],
            email=email,
            phone=phone[:50] if phone else None,
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
    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).filter(Supplier.archived_at.is_(None)).first_or_404()
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
    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).filter(Supplier.archived_at.is_(None)).first_or_404()

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower() or None
        phone = (request.form.get('phone') or '').strip() or None
        if len(name) < 2 or (email and ('@' not in email or len(email) > 120)):
            flash('Revisa el nombre y el correo del proveedor.', 'danger')
            return redirect(request.url)
        supplier.name = name[:150]
        supplier.email = email
        supplier.phone = phone[:50] if phone else None

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

    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).filter(Supplier.archived_at.is_(None)).first_or_404()

    from datetime import datetime
    supplier.archived_at = utcnow()
    db.session.commit()
    flash('Proveedor enviado a la papelera', 'info')
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
    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id, archived_at=None).first_or_404()

    user = User.query.get(user_id)
    can_purchases = bool(user and user.has_permission('purchases.view'))

    # El historial de compras se expone solo a perfiles autorizados para compras.
    orders = PurchaseOrder.query.filter_by(
        supplier_id=supplier_id,
        company_id=company_id
    ).order_by(
        PurchaseOrder.created_at.desc()
    ).all() if can_purchases else []

    total_spent = sum(
        (o.total_cost or Decimal('0.00'))
        for o in orders
    )
    can_finance = bool(user and user.has_permission('finance.payables'))
    can_documents = bool(user and user.has_permission('company.documents'))
    bills = SupplierBill.query.filter_by(company_id=company_id, supplier_id=supplier.id).order_by(SupplierBill.created_at.desc()).all() if can_finance else []
    outstanding = sum((bill.balance for bill in bills), Decimal('0.00')) if can_finance else None
    payments = SupplierPayment.query.join(SupplierBill, SupplierPayment.bill_id == SupplierBill.id).filter(
        SupplierPayment.company_id == company_id, SupplierBill.supplier_id == supplier.id
    ).order_by(SupplierPayment.created_at.desc()).limit(30).all() if can_finance else []
    documents = CompanyDocument.query.filter_by(company_id=company_id, entity_type='SUPPLIER', entity_id=supplier.id).order_by(CompanyDocument.created_at.desc()).all() if can_documents else []

    return render_template(
        'suppliers/supplier_history.html',
        supplier=supplier,
        orders=orders,
        total_spent=total_spent, outstanding=outstanding, bills=bills, payments=payments, documents=documents,
        user=user, can_purchases=can_purchases, can_finance=can_finance, can_documents=can_documents
    )
