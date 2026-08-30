from flask import request, session, flash, redirect, url_for, current_app, jsonify, g
from decimal import Decimal
from datetime import timedelta

from db import db
from models.sales.sales import Sale
from models.company.company import Company
from models.user.user import User
from models.retail import SalePayment, GiftCard
from services.time_utils import utcnow
from services.quantity import as_decimal
from services.validation import BusinessRuleError
from services.retail import (
    ensure_credit_allowed, get_retail_settings, reserve_serials_for_item,
    loyalty_redemption_quote, redeem_loyalty,
)
from services.sale_engine import finalize_sale_inventory_and_loyalty
from services.webhooks import emit_event
from .core import recalc_sale, resolve_sale_warehouse
from .sales import sales_bp
from .access import editable_sales_query


def _money(raw, label):
    try:
        value = as_decimal(raw or 0).quantize(Decimal('0.01'))
    except Exception as exc:
        raise BusinessRuleError(f'{label} no es válido.') from exc
    if value < 0:
        raise BusinessRuleError(f'{label} no puede ser negativo.')
    return value


def _payment_plan(sale, settings):
    method = (request.form.get('payment_method') or 'CASH').upper()
    total = as_decimal(sale.total).quantize(Decimal('0.01'))
    reference = (request.form.get('payment_reference') or '').strip() or None
    parts = []
    gift_card = None
    loyalty_points = Decimal('0.0000')

    if method != 'MIXED':
        if method not in {'CASH','CARD','TRANSFER','CREDIT'}:
            method = 'CASH'
        parts = [(method, total, reference, None)]
    else:
        for field, part_method in (('cash_amount','CASH'),('card_amount','CARD'),('transfer_amount','TRANSFER'),('credit_amount','CREDIT')):
            amount = _money(request.form.get(field), field.replace('_',' ').title())
            if amount > 0:
                parts.append((part_method, amount, reference if part_method in {'CARD','TRANSFER'} else None, None))
        gift_amount = _money(request.form.get('gift_card_amount'), 'Monto gift card')
        if gift_amount > 0:
            code = (request.form.get('gift_card_code') or '').strip().upper()
            if not code:
                raise BusinessRuleError('Indica el código de la gift card.')
            gift_card = GiftCard.query.filter_by(company_id=sale.company_id, code=code, status='ACTIVE').with_for_update().first()
            if not gift_card:
                raise BusinessRuleError('La gift card no existe o no está activa.')
            if gift_card.expires_at and gift_card.expires_at < utcnow().date():
                gift_card.status = 'EXPIRED'
                raise BusinessRuleError('La gift card está vencida.')
            if as_decimal(gift_card.balance) < gift_amount:
                raise BusinessRuleError(f'Saldo insuficiente en gift card. Disponible {gift_card.balance}.')
            parts.append(('GIFT_CARD', gift_amount, code, gift_card))
        raw_points = request.form.get('loyalty_points') or 0
        if as_decimal(raw_points) > 0:
            already_planned = sum((amount for _, amount, _, _ in parts), Decimal('0'))
            remaining = max(total - already_planned, Decimal('0.00'))
            loyalty_points, loyalty_amount = loyalty_redemption_quote(
                sale.client, raw_points, settings, max_amount=remaining,
            )
            if loyalty_amount > 0:
                parts.append(('LOYALTY', loyalty_amount, f'{loyalty_points:.4f} pts', None))
        if not parts:
            raise BusinessRuleError('Indica al menos un medio de pago.')
        planned = sum((amount for _, amount, _, _ in parts), Decimal('0'))
        if planned != total:
            raise BusinessRuleError(f'El pago dividido suma {planned:.2f} y la venta totaliza {total:.2f}.')

    credit = sum((amount for part_method, amount, _, _ in parts if part_method == 'CREDIT'), Decimal('0'))
    if credit > 0:
        ensure_credit_allowed(sale.client, credit)

    # Preserve the physical cash tender independently from the amount applied
    # to the sale. For old/API clients that don't send cash_received we default
    # to exact payment, keeping backwards compatibility with zero change.
    cash_due = sum(
        (amount for part_method, amount, _reference, _card in parts if part_method == 'CASH'),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))
    if cash_due > 0:
        raw_received = request.form.get('cash_received')
        received = cash_due if raw_received in (None, '') else _money(raw_received, 'Efectivo recibido')
        if received < cash_due:
            raise BusinessRuleError(
                f'El efectivo recibido ({received:.2f}) no cubre el monto en efectivo ({cash_due:.2f}).'
            )
        if received > Decimal('9999999999.99'):
            raise BusinessRuleError('El efectivo recibido excede el límite permitido.')
        sale.cash_received = received
        sale.cash_change = (received - cash_due).quantize(Decimal('0.01'))
    else:
        sale.cash_received = None
        sale.cash_change = Decimal('0.00')

    paid = total - credit
    return method, paid, credit, parts, loyalty_points


@sales_bp.route('/finish', methods=['POST'])
def finish_sale():
    """Finalize the active POS sale, including walk-in/consumer-final sales.

    A registered client is optional for cash, card and transfer payments. Credit,
    loyalty redemption and layaway remain client-bound and are rejected with a
    precise business message. AJAX callers receive JSON so the POS can keep the
    operator in context instead of falling into a generic error page.
    """
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    user_id = session.get('user_id')
    wants_json = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )
    create_url = url_for('sales_bp.create_sale')

    def reject(message, status=400, category='danger', redirect_url=None):
        destination = redirect_url or create_url
        if wants_json:
            return jsonify(
                ok=False,
                error=message,
                redirect=destination,
                request_id=getattr(g, 'request_id', None),
            ), status
        flash(message, category)
        return redirect(destination)

    if not company_id or not sale_id or not user_id:
        return reject(
            'La sesión de venta expiró. Inicia sesión nuevamente para continuar.',
            401,
            redirect_url=url_for('login_bp.login'),
        )

    company = Company.query.filter_by(id=company_id).with_for_update().first()
    if not company:
        return reject(
            'La empresa de esta sesión ya no está disponible.',
            403,
            redirect_url=url_for('login_bp.login'),
        )
    limits = company.get_plan_limits()
    if company.get_current_month_usage() >= limits['max_monthly_invoices']:
        return reject(
            f'Límite de facturación alcanzado ({limits["max_monthly_invoices"]} facturas/mes). Solicita un upgrade.',
            409,
            'warning',
        )

    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).with_for_update().first()
    if not sale:
        session.pop('current_sale_id', None)
        return reject('La venta activa ya no existe. Inicia un pedido nuevo.', 404, 'warning')
    if sale.status == 'COMPLETED':
        session.pop('current_sale_id', None)
        destination = url_for('sales_bp.sale_detail', sale_id=sale.id)
        if wants_json:
            return jsonify(
                ok=True,
                message='La venta ya había sido finalizada.',
                redirect=destination,
                sale_id=sale.id,
            )
        flash('La venta ya había sido finalizada.', 'info')
        return redirect(destination)
    if sale.status not in {'DRAFT', 'PENDING', 'QUOTATION'}:
        return reject(
            'El estado actual de la venta no permite finalizarla.',
            409,
            'warning',
            url_for('sales_bp.list_sales'),
        )
    if int(sale.user_id) != int(user_id):
        return reject(
            'No tienes permiso para finalizar esta venta.',
            403,
            redirect_url=url_for('sales_bp.list_sales'),
        )
    if not sale.items:
        return reject('Agrega al menos un producto antes de confirmar la venta.', 409, 'warning')

    user = User.query.filter_by(id=user_id, company_id=company_id).first()
    if not user:
        return reject(
            'Tu usuario ya no está disponible en esta empresa.',
            403,
            redirect_url=url_for('login_bp.logout'),
        )

    try:
        assigned = resolve_sale_warehouse(user, company_id, sale=None) if user.warehouse_id else None
        origin_ids = {int(item.warehouse_id) for item in sale.items if item.warehouse_id}
        if len(origin_ids) > 1:
            raise BusinessRuleError('La venta contiene artículos de varios almacenes.')
        if assigned and any(item.warehouse_id and int(item.warehouse_id) != assigned.id for item in sale.items):
            raise BusinessRuleError(
                f'Esta cuenta está asignada a {assigned.name}; la venta contiene artículos de otro almacén.'
            )

        recalc_sale(sale)
        settings = get_retail_settings(company_id, create=True)
        payment_method, amount_paid, balance, parts, loyalty_points = _payment_plan(sale, settings)
        for item in sale.items:
            reserve_serials_for_item(item)

        sale.payment_method = payment_method if payment_method != 'MIXED' else 'MIXED'
        sale.amount_paid = amount_paid
        sale.balance = balance
        sale.status = 'COMPLETED'
        sale.created_at = utcnow()
        sale.customer_name = sale.client.name if sale.client else (sale.customer_name or 'Consumidor final')
        if loyalty_points > 0:
            redeem_loyalty(sale.client, sale, loyalty_points, settings)
        finalize_sale_inventory_and_loyalty(sale, settings=settings)

        for part_method, amount, reference, card in parts:
            if card:
                card.balance = as_decimal(card.balance) - amount
                if card.balance <= 0:
                    card.balance = Decimal('0.00')
                    card.status = 'DEPLETED'
            db.session.add(SalePayment(
                company_id=company_id,
                sale_id=sale.id,
                method=part_method,
                amount=amount,
                reference=reference,
                gift_card_id=card.id if card else None,
            ))
        db.session.commit()
        session.pop('current_sale_id', None)
        try:
            emit_event(company_id, 'sale.completed', {
                'sale_id': sale.id,
                'total': str(sale.total),
                'client_id': sale.client_id,
                'terminal_id': sale.terminal_id,
                'branch_id': sale.branch_id,
            })
        except Exception:
            # The sale is already committed. A notification/integration failure
            # must never tell the cashier that the sale failed or invite a
            # duplicate retry.
            current_app.logger.exception(
                'Sale webhook scheduling failed after commit company_id=%s sale_id=%s',
                company_id, sale.id,
            )
        destination = url_for('sales_bp.sale_detail', sale_id=sale.id)
        message = f'Venta #{sale.id} finalizada exitosamente.'
        if wants_json:
            return jsonify(ok=True, message=message, redirect=destination, sale_id=sale.id)
        flash(message, 'success')
        return redirect(destination)
    except BusinessRuleError as exc:
        db.session.rollback()
        return reject(str(exc), 409, 'warning')
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            'Unexpected POS finish failure request_id=%s company_id=%s sale_id=%s',
            getattr(g, 'request_id', None), company_id, sale_id,
        )
        return reject(
            'No fue posible finalizar la venta por un error interno. No se descontó inventario ni se registró el pago. '
            'Actualiza la caja y vuelve a intentarlo; si continúa, comparte la referencia mostrada.',
            500,
        )


# ==========================================================
# CANCELAR VENTA
# ==========================================================
@sales_bp.route('/cancel/<int:sale_id>', methods=['POST'])
def cancel_sale(sale_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    
    sale = editable_sales_query(company_id, user_id).filter_by(id=sale_id).first_or_404()

    if sale.status not in ['PENDING', 'QUOTATION']:
        flash('No se pueden cancelar ventas finalizadas', 'warning')
        return redirect(url_for('sales_bp.list_sales'))

    sale.status = 'CANCELLED'
    
    if session.get('current_sale_id') == sale.id:
        session.pop('current_sale_id', None)

    db.session.commit()
    flash(f'Venta #{sale.id} cancelada', 'info')
    return redirect(url_for('sales_bp.list_sales'))

# ==========================================================
# CONVERTIR EN COTIZACIÓN (MANTENIENDO RELACIONES DE OBJETOS)
# ==========================================================
@sales_bp.route('/quote/<int:sale_id>', methods=['POST'])
def convert_to_quote(sale_id):
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    
    sale = editable_sales_query(company_id, user_id).filter_by(id=sale_id).first_or_404()

    if not sale.items:
        flash('No puedes cotizar una venta sin productos', 'warning')
        return redirect(url_for('sales_bp.create_sale'))
    
    sale.status = 'QUOTATION'
    if not sale.quote_valid_until:
        sale.quote_valid_until = (utcnow() + timedelta(days=15)).date()
    
    # Recalculamos totales antes de asentar el estado intermedio
    recalc_sale(sale)
    
    try:
        db.session.commit()
        # Remover de la sesión activa de creación de manera segura
        if session.get('current_sale_id') == sale.id:
            session.pop('current_sale_id', None)
        
        flash(f'Venta #{sale.id} guardada como Cotización con {len(sale.items)} ítems vinculados', 'success')
        return redirect(url_for('sales_bp.list_sales'))
    except Exception:
        db.session.rollback()
        current_app.logger.exception('No se pudo guardar la cotización %s', sale.id)
        flash('No se pudo guardar la cotización. No se aplicó ningún cambio.', 'danger')
        return redirect(url_for('sales_bp.create_sale'))
