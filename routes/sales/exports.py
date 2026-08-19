from flask import render_template, session, abort, make_response, request, redirect, url_for, flash
from models.sales.sales import Sale
from models.company.company import Company
from models.divisas.divisas import ExchangeRate # Importante
from decimal import Decimal # Importante para evitar el TypeError
import pdfkit
import os
import base64
import platform

# IMPORTANTE: Importamos el blueprint único definido en sales.py
from .sales import sales_bp

@sales_bp.route('/pdf/<int:sale_id>')
def export_pdf(sale_id):
    company_id = session.get('company_id')
    if not company_id:
        abort(403)

    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).first_or_404()
    from db import db
    company = db.session.get(Company, company_id)
    
    # --- LÓGICA DE DIVISA PARA PDF ---
    selected_currency = session.get('selected_currency', 'DOP')
    
    rate_val = ExchangeRate.get_rate(selected_currency, company_id)
    
    conversion_rate = Decimal(str(rate_val))
    
    rate_row = ExchangeRate.query.filter_by(currency_code=selected_currency, company_id=company_id).first()
    currency_symbol = rate_row.symbol if rate_row else 'RD$'

    # --- Lógica de Logo a Base64 ---
    logo_base64 = None
    if company and company.logo:
        basedir = os.path.abspath(os.path.dirname(__file__))
        path_logo = os.path.join(basedir, '..', '..', 'static', company.logo)
        path_logo = os.path.normpath(path_logo)

        if os.path.exists(path_logo):
            try:
                with open(path_logo, "rb") as image_file:
                    raw_encoded = base64.b64encode(image_file.read()).decode('utf-8')
                    logo_base64 = f"data:image/png;base64,{raw_encoded}"
            except Exception as e:
                print(f"Error cargando logo para PDF: {e}")

    # Enviamos las nuevas variables al template
    html_rendered = render_template(
        'sales/invoice_pdf.html', 
        sale=sale, 
        company=company, 
        logo_exists=logo_base64,
        selected_currency=selected_currency,
        currency_symbol=currency_symbol,
        conversion_rate=conversion_rate
    )

    options = {
        'page-size': 'Letter',
        'encoding': "UTF-8",
        'enable-local-file-access': None,
        'quiet': ''
    }
    
    try:
        if platform.system() == "Windows":
            path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
            config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
            pdf = pdfkit.from_string(html_rendered, False, options=options, configuration=config)
        else:
            pdf = pdfkit.from_string(html_rendered, False, options=options)
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=Factura_{sale.id}.pdf'
        return response

    except Exception as e:
        return f"Error generando PDF: {str(e)}", 500
