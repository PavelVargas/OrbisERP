from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models.category.category import Category
from db import db
from models.user.user import User
from models.products.products import Product
from sqlalchemy import func

category_bp = Blueprint('category_bp', __name__, url_prefix='/category')

# =========================
# LISTAR CATEGORÍAS
# =========================
@category_bp.route('/')
def list_categories():
    user_id = session.get('user_id') 
    company_id = session.get('company_id')

    if not user_id or not company_id:
        flash('Debes iniciar sesión y tener una empresa activa', 'warning')
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)

    search = (request.args.get('search') or '').strip()
    query = Category.query.filter_by(status=True, company_id=company_id)
    if search:
        query = query.filter(Category.name.ilike(f'%{search}%'))
    categories = query.order_by(Category.name.asc()).all()
    product_counts = dict(db.session.query(Product.category_id, func.count(Product.id)).filter(
        Product.company_id == company_id, Product.status.is_(True)
    ).group_by(Product.category_id).all())

    return render_template('categories/category.html', categories=categories, user=user,
                           product_counts=product_counts, search=search)

# =========================
# CREAR CATEGORÍA
# =========================
@category_bp.route('/create', methods=['GET', 'POST'])
def create_category():
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    
    if not company_id:
        flash('Acceso denegado', 'error')
        return redirect(url_for('login_bp.login'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()

        if not name:
            flash('El nombre es obligatorio', 'error')
            return redirect(url_for('category_bp.create_category'))

        duplicate = Category.query.filter(Category.company_id == company_id,
            db.func.lower(Category.name) == name.lower()).first()
        if duplicate:
            flash('Ya existe una categoría con ese nombre', 'warning')
            return redirect(url_for('category_bp.create_category'))
        category = Category(
            name=name,
            company_id=company_id
        )

        db.session.add(category)
        db.session.commit()

        flash('Categoría creada correctamente', 'success')
        return redirect(url_for('category_bp.list_categories'))

    # Necesitamos pasar el objeto 'user' para que el left_bar funcione
    user = User.query.get(user_id)
    return render_template('categories/create.html', user=user)


@category_bp.route('/api/create', methods=['POST'])
def create_category_api():
    """Create a category without leaving a product form."""
    company_id = session.get('company_id')
    if not session.get('user_id') or not company_id:
        return jsonify({'error': 'Autenticación requerida'}), 401

    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()
    if len(name) < 2 or len(name) > 100:
        return jsonify({'error': 'Escribe un nombre de 2 a 100 caracteres.'}), 400

    existing = Category.query.filter(
        Category.company_id == company_id,
        db.func.lower(Category.name) == name.lower()
    ).first()
    if existing:
        if not existing.status:
            existing.status = True
            db.session.commit()
        return jsonify({'id': existing.id, 'name': existing.name, 'existing': True})

    category = Category(name=name, company_id=company_id, status=True)
    db.session.add(category)
    db.session.commit()
    return jsonify({'id': category.id, 'name': category.name, 'existing': False}), 201

# =========================
# EDITAR CATEGORÍA
# =========================
@category_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_category(id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')

    if not company_id:
        return redirect(url_for('login_bp.login'))

    category = Category.query.filter_by(
        id=id,
        company_id=company_id
    ).first_or_404()

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if len(name) < 2 or len(name) > 100:
            flash('Escribe un nombre de 2 a 100 caracteres', 'warning')
            return redirect(request.url)
        duplicate = Category.query.filter(Category.company_id == company_id,
            db.func.lower(Category.name) == name.lower(), Category.id != category.id).first()
        if duplicate:
            flash('Ya existe una categoría con ese nombre', 'warning')
            return redirect(request.url)
        category.name = name
        db.session.commit()

        flash('Categoría actualizada', 'success')
        return redirect(url_for('category_bp.list_categories'))

    user = User.query.get(user_id)
    return render_template('categories/edit.html', category=category, user=user)

# =========================
# ELIMINAR (SOFT DELETE)
# =========================
@category_bp.route('/delete/<int:id>', methods=['POST'])
def delete_category(id):
    company_id = session.get('company_id')
    if not company_id:
        return redirect(url_for('login_bp.login'))

    category = Category.query.filter_by(
        id=id,
        company_id=company_id
    ).first_or_404()

    category.status = False
    db.session.commit()

    flash('Categoría desactivada', 'info')
    return redirect(url_for('category_bp.list_categories'))
