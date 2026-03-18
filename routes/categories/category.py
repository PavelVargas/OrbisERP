from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models.category.category import Category
from db import db
from models.user.user import User

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

    categories = Category.query \
        .filter_by(
            status=True,
            company_id=company_id
        ) \
        .order_by(Category.created_at.desc()) \
        .all()

    return render_template('categories/category.html', categories=categories, user=user)

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
        name = request.form.get('name')

        if not name:
            flash('El nombre es obligatorio', 'error')
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
        category.name = request.form.get('name')
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