from flask import (
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from db import db
from models.company.company import Company
from models.divisas.divisas import ExchangeRate
from models.retail import CompanyRetailSettings
from services.numeric import finite_decimal
from services.validation import BusinessRuleError
from services.sales_pdf import build_sale_invoice_pdf

from .access import visible_sales_query
from .sales import sales_bp


def _document_exchange_rate(selected_currency, company_id):
    """Resolve a verified rate for financial documents without silent 1:1 fallback."""
    try:
        rate = finite_decimal(
            ExchangeRate.get_rate(selected_currency, company_id),
            field_name='Tasa de conversión',
        )
        if rate <= 0:
            raise BusinessRuleError('La tasa de conversión debe ser mayor que cero.')
        return rate
    except (BusinessRuleError, RuntimeError, TypeError, ValueError) as exc:
        current_app.logger.warning(
            'No se pudo resolver la tasa para documento; company_id=%s currency=%s: %s',
            company_id,
            selected_currency,
            exc,
        )
        return None


def _currency_context(selected_currency, company_id):
    rate = _document_exchange_rate(selected_currency, company_id)
    if rate is None:
        return None, None
    rate_row = ExchangeRate.query.filter_by(
        currency_code=selected_currency,
        company_id=company_id,
    ).first()
    symbol = rate_row.symbol if rate_row else 'RD$'
    return rate, symbol


@sales_bp.route('/pdf/<int:sale_id>')
def export_pdf(sale_id):
    company_id = session.get('company_id')
    if not company_id:
        abort(403)

    sale = visible_sales_query(company_id, session.get('user_id')).filter_by(id=sale_id).first_or_404()
    company = db.session.get(Company, company_id)
    selected_currency = session.get('selected_currency', 'DOP')
    conversion_rate, currency_symbol = _currency_context(selected_currency, company_id)
    if conversion_rate is None:
        flash(
            f'No hay una tasa válida para {selected_currency}. Configúrala antes de generar el documento.',
            'danger',
        )
        return redirect(url_for('sales_bp.sale_detail', sale_id=sale.id))

    try:
        pdf = build_sale_invoice_pdf(
            sale=sale,
            company=company,
            static_folder=current_app.static_folder,
            selected_currency=selected_currency,
            currency_symbol=currency_symbol,
            conversion_rate=conversion_rate,
        )
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        document_kind = 'Cotizacion' if sale.status == 'QUOTATION' else 'Factura'
        response.headers['Content-Disposition'] = f'inline; filename={document_kind}_{sale.id}.pdf'
        response.headers['Cache-Control'] = 'private, no-store, max-age=0'
        return response
    except Exception:
        current_app.logger.exception('No se pudo generar el PDF de la venta %s', sale.id)
        flash('No se pudo generar el PDF de esta venta. Inténtalo nuevamente.', 'danger')
        return redirect(url_for('sales_bp.sale_detail', sale_id=sale.id))


@sales_bp.route('/receipt/<int:sale_id>')
def thermal_receipt(sale_id):
    """Browser-native 58/80 mm receipt; ideal for Electron/thermal POS."""
    company_id = session.get('company_id')
    if not company_id:
        abort(403)

    sale = visible_sales_query(company_id, session.get('user_id')).filter_by(id=sale_id).first_or_404()
    company = db.session.get(Company, company_id)
    settings = db.session.get(CompanyRetailSettings, company_id)
    selected_currency = session.get('selected_currency', 'DOP')
    conversion_rate, currency_symbol = _currency_context(selected_currency, company_id)
    if conversion_rate is None:
        flash(
            f'No hay una tasa válida para {selected_currency}. Configúrala antes de imprimir el recibo.',
            'danger',
        )
        return redirect(url_for('sales_bp.sale_detail', sale_id=sale.id))

    default_width = (
        sale.terminal.receipt_width
        if getattr(sale, 'terminal', None)
        else (settings.default_receipt_width if settings else 80)
    )
    requested_width = request.args.get('width', type=int)
    width = requested_width if requested_width is not None else int(default_width or 80)
    width = max(40, min(112, width))
    requested_autoprint = request.args.get('autoprint')
    autoprint = (requested_autoprint == '1') if requested_autoprint is not None else bool(settings and settings.receipt_auto_print)
    return render_template(
        'sales/receipt_thermal.html',
        sale=sale,
        company=company,
        width=width,
        selected_currency=selected_currency,
        currency_symbol=currency_symbol,
        conversion_rate=conversion_rate,
        autoprint=autoprint,
        printer_mode=(settings.receipt_printer_mode if settings else 'BROWSER'),
        printer_name=(settings.receipt_printer_name if settings else None),
    )
