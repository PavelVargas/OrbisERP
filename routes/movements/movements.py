from flask import Blueprint, render_template, request, session, redirect, url_for
from models.stock_movement.stock_movement import StockMovement
from models.products.products import Product
from models.user.user import User
from db import db

movements_bp = Blueprint('movements_bp', __name__, url_prefix='/movements')

# ===============================
# ENTRADAS
# ===============================
@movements_bp.route('/in')
def movements_in():
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    product_id = request.args.get('product_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    query = StockMovement.query.filter_by(movement_type='IN', company_id=company_id)

    if product_id:
        query = query.filter(StockMovement.product_id == product_id)

    if date_from:
        query = query.filter(StockMovement.created_at >= date_from)

    if date_to:
        query = query.filter(StockMovement.created_at <= date_to)

    movements = query.order_by(StockMovement.created_at.desc()).all()
    
    products = Product.query.filter_by(status=True, company_id=company_id).all()

    return render_template(
        'movements/entries.html',
        movements=movements,
        products=products,
        product_id=product_id,
        date_from=date_from,
        date_to=date_to,
        user=user 
    )

# ===============================
# SALIDAS
# ===============================
@movements_bp.route('/out')
def movements_out():
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    product_id = request.args.get('product_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    query = StockMovement.query.filter_by(movement_type='OUT', company_id=company_id)

    if product_id:
        query = query.filter(StockMovement.product_id == product_id)

    if date_from:
        query = query.filter(StockMovement.created_at >= date_from)

    if date_to:
        query = query.filter(StockMovement.created_at <= date_to)

    movements = query.order_by(StockMovement.created_at.desc()).all()
    
    products = Product.query.filter_by(status=True, company_id=company_id).all()

    return render_template(
        'movements/exits.html',
        movements=movements,
        products=products,
        product_id=product_id,
        date_from=date_from,
        date_to=date_to,
        user=user 
    )