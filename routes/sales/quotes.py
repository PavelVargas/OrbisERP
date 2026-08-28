from datetime import date, datetime, timedelta

from flask import flash, redirect, render_template, request, session, url_for

from db import db
from models.sales.sales import Sale
from models.user.user import User
from .core import recalc_sale
from .access import can_view_all_sales, editable_sales_query, visible_sales_query
from .sales import sales_bp


@sales_bp.get('/quotes')
def quotes():
    # Compatibilidad: las cotizaciones viven en la vista única de Ventas.
    return redirect(url_for('sales_bp.list_sales', status='QUOTATION'))


@sales_bp.post('/quotes/<int:sale_id>/update')
def quote_update(sale_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    quote = editable_sales_query(company_id, user_id).filter_by(id=sale_id, status='QUOTATION').with_for_update().first_or_404()
    raw = (request.form.get('valid_until') or '').strip()
    try:
        quote.quote_valid_until = datetime.strptime(raw, '%Y-%m-%d').date() if raw else None
    except ValueError:
        flash('La fecha de vigencia no es válida.', 'danger')
        return redirect(url_for('sales_bp.list_sales', status='QUOTATION'))
    quote.quote_notes = (request.form.get('notes') or '').strip()[:500] or None
    recalc_sale(quote)
    db.session.commit()
    flash(f'Cotización #{quote.id} actualizada.', 'success')
    return redirect(url_for('sales_bp.list_sales', status='QUOTATION'))


@sales_bp.post('/quotes/<int:sale_id>/convert')
def quote_convert(sale_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    quote = editable_sales_query(company_id, user_id).filter_by(id=sale_id, status='QUOTATION').with_for_update().first_or_404()
    if quote.quote_valid_until and quote.quote_valid_until < date.today():
        flash('La cotización está vencida. Actualiza su vigencia antes de convertirla.', 'warning')
        return redirect(url_for('sales_bp.list_sales', status='QUOTATION'))
    quote.status = 'PENDING'
    quote.user_id = session.get('user_id')
    recalc_sale(quote)
    db.session.commit()
    session['current_sale_id'] = quote.id
    flash(f'Cotización #{quote.id} convertida a venta pendiente. Revisa y confirma el cobro.', 'success')
    return redirect(url_for('sales_bp.create_sale'))


@sales_bp.post('/promotion/apply')
def apply_promotion():
    from models.productivity import Promotion
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    sale = editable_sales_query(company_id, session.get('user_id')).filter_by(id=sale_id).with_for_update().first_or_404()
    code = (request.form.get('code') or '').strip().upper()
    promotion = Promotion.query.filter_by(company_id=company_id, code=code, active=True).first()
    gross = sum((item.quantity or 0) * (item.price or 0) for item in sale.items)
    if not promotion or not promotion.is_available(subtotal=gross):
        flash('El código no existe, no está vigente o no alcanza la compra mínima.', 'warning')
    else:
        # Assign the relationship as well as the FK. recalc_sale() runs before
        # commit, so relying on a lazy refresh would silently skip the discount.
        sale.promotion = promotion
        sale.promotion_id = promotion.id
        recalc_sale(sale)
        db.session.commit()
        flash(f'Promoción {promotion.code} aplicada.', 'success')
    return redirect(url_for('sales_bp.create_sale'))


@sales_bp.post('/promotion/remove')
def remove_promotion():
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    sale = editable_sales_query(company_id, session.get('user_id')).filter_by(id=sale_id).with_for_update().first_or_404()
    sale.promotion = None
    sale.promotion_id = None
    recalc_sale(sale)
    db.session.commit()
    flash('Promoción retirada.', 'info')
    return redirect(url_for('sales_bp.create_sale'))
