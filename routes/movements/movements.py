from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, session, redirect, url_for
from models.stock_movement.stock_movement import StockMovement
from models.products.products import Product
from models.user.user import User

movements_bp = Blueprint('movements_bp', __name__, url_prefix='/movements')


def _movement_context(movement_type):
    """Build a tenant-scoped inventory movement query with validated filters."""
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return None

    user = User.query.get(user_id)
    if not user:
        session.clear()
        return None

    product_id = request.args.get('product_id', type=int)
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    query = StockMovement.query.filter_by(movement_type=movement_type, company_id=company_id)

    if product_id:
        query = query.filter(StockMovement.product_id == product_id)

    try:
        if date_from:
            query = query.filter(StockMovement.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        if date_to:
            # Exclusive next-day boundary includes the entire selected end date.
            query = query.filter(StockMovement.created_at < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
        if date_from and date_to and date_from > date_to:
            date_from = date_to = ''
            query = StockMovement.query.filter_by(movement_type=movement_type, company_id=company_id)
            if product_id:
                query = query.filter(StockMovement.product_id == product_id)
    except ValueError:
        date_from = date_to = ''
        query = StockMovement.query.filter_by(movement_type=movement_type, company_id=company_id)
        if product_id:
            query = query.filter(StockMovement.product_id == product_id)

    movements = query.order_by(StockMovement.created_at.desc()).all()
    products = Product.query.filter_by(status=True, company_id=company_id).filter(Product.archived_at.is_(None)).order_by(Product.name.asc()).all()
    return {
        'movements': movements,
        'products': products,
        'product_id': product_id,
        'date_from': date_from,
        'date_to': date_to,
        'user': user,
    }


@movements_bp.route('/in')
def movements_in():
    context = _movement_context('IN')
    if context is None:
        return redirect(url_for('login_bp.login'))
    return render_template('movements/entries.html', **context)


@movements_bp.route('/out')
def movements_out():
    context = _movement_context('OUT')
    if context is None:
        return redirect(url_for('login_bp.login'))
    return render_template('movements/exits.html', **context)
