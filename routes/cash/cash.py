from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models.sales.sales import Sale
from models.cash.cash_closing import CashClosing 
from models.user.user import User
from models.divisas.divisas import ExchangeRate
from db import db
from sqlalchemy import func
from datetime import datetime, time

cash_bp = Blueprint('cash_bp', __name__, url_prefix='/cash')


@cash_bp.route('/close', methods=['GET', 'POST'])
def close_cash():

    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    # 1️⃣ Moneda seleccionada (solo código)
    selected_currency = session.get('selected_currency', 'DOP')

    # 2️⃣ Obtener datos reales desde la DB
    rate_data = ExchangeRate.query.filter_by(currency_code=selected_currency).first()

    if rate_data:
        currency_symbol = rate_data.symbol
        conversion_rate = float(rate_data.rate)
    else:
        currency_symbol = selected_currency
        conversion_rate = 1.0

    # seguridad extra
    conversion_rate = conversion_rate if conversion_rate else 1.0

    user = db.session.get(User, user_id)

    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)

    # 3️⃣ Ventas del día
    stats = db.session.query(
        func.sum(Sale.amount_paid).label('cash_received'), 
        func.sum(Sale.balance).label('pending_credit'),   
        func.count(Sale.id).label('ticket_count')
    ).filter(
        Sale.user_id == user_id,
        Sale.company_id == company_id,
        Sale.status.in_(['COMPLETED', 'PENDING']),
        Sale.created_at >= today_start 
    ).first()

    cash_received = float(stats.cash_received or 0)
    pending_credit = float(stats.pending_credit or 0)

    # 4️⃣ Conversión
    system_total_converted = cash_received / conversion_rate
    credit_total_converted = pending_credit / conversion_rate
    total_tickets_count = stats.ticket_count or 0

    if request.method == 'POST':

        reported = request.form.get('reported_amount', type=float) or 0
        notes = request.form.get('notes', "")

        difference = reported - system_total_converted

        audit_note = f"{notes} | Audit: {selected_currency} Rate {conversion_rate}"

        new_closing = CashClosing(
            company_id=company_id,
            user_id=user_id,
            opening_date=today_start,
            closing_date=now,
            system_amount=system_total_converted,
            reported_amount=reported,
            difference=difference,
            notes=audit_note
        )

        db.session.add(new_closing)
        db.session.commit()

        # 5️⃣ Alertas
        if abs(difference) < 0.01:
            flash(f'Caja cuadrada en {selected_currency}', 'success')
        else:
            status = "FALTANTE" if difference < 0 else "SOBRANTE"
            flash(f'Cierre con {status} de {currency_symbol} {abs(difference):,.2f}', 'warning')

        return redirect(url_for('dashboard_bp.dashboard'))

    return render_template(
        'cash/close.html',
        system_total=system_total_converted,
        credit_total=credit_total_converted,
        total_tickets_count=total_tickets_count,
        user=user,
        selected_currency=selected_currency,
        currency_symbol=currency_symbol,
        conversion_rate=conversion_rate
    )