import io
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from flask import (
    Blueprint, render_template, session, redirect, 
    url_for, Response, send_file, request, flash
)
from sqlalchemy import func, extract, and_, or_
from sqlalchemy.orm import joinedload
from fpdf import FPDF

from db import db
from models.sales.sales import Sale
from models.cash.cash_closing import CashClosing
from models.products.products import Product
from models.user.user import User
from models.divisas.divisas import ExchangeRate

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

reports_bp = Blueprint('reports_bp', __name__, url_prefix='/reports')

# ==============================================================================
# CLASE BASE PARA PDF CORPORATIVO (MEJORADA)
# ==============================================================================

class OrbisPDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.company_name = "OrbisERP Cloud"
        self.report_type = "Reporte General"

    def header(self):
        # Color de fondo superior decorativo
        self.set_fill_color(250, 162, 0) # Naranja Orbis
        self.rect(0, 0, 210, 10, 'F')
        
        self.set_y(15)
        self.set_font("helvetica", "B", 18)
        self.set_text_color(40, 40, 40)
        self.cell(0, 12, "ORBIS ERP", ln=True, align="L")
        
        self.set_font("helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, self.report_type.upper(), ln=True, align="L")
        
        self.set_font("helvetica", "I", 8)
        cid = session.get('company_id', 'N/A')
        gen_date = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        selected_curr = session.get('selected_currency', 'DOP')
        self.cell(0, 5, f"Empresa ID: {cid} | Fecha: {gen_date} | Moneda: {selected_curr}", ln=True, align="L")
        
        self.set_draw_color(250, 162, 0)
        self.set_line_width(0.5)
        self.line(10, 42, 200, 42)
        self.ln(15)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        footer_text = f"Documento generado por OrbisERP. Página {self.page_no()}/{{nb}}"
        self.cell(0, 10, footer_text, align="C")

    def safe_text(self, text):
        if not text: return ""
        return str(text).encode('latin-1', 'ignore').decode('latin-1')

# ==============================================================================
# UTILIDADES DE SOPORTE (TU LÓGICA ORIGINAL)
# ==============================================================================

def get_company_context():
    company_id = session.get('company_id')
    if not company_id:
        return None, None, Decimal('1.0')

    selected_currency = session.get('selected_currency', 'DOP')
    exchange = db.session.query(ExchangeRate).filter_by(
        company_id=company_id,
        currency_code=selected_currency
    ).first()

    if exchange:
        symbol = exchange.symbol
        rate = Decimal(str(exchange.rate))
    else:
        symbol = "RD$"
        rate = Decimal('1.0')

    return company_id, symbol, rate

def build_pdf_response(pdf_obj, filename_prefix):
    try:
        pdf_bytes = pdf_obj.output(dest='S')
        if isinstance(pdf_bytes, str):
            pdf_bytes = pdf_bytes.encode('latin-1')
        output = io.BytesIO(pdf_bytes)
        output.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{filename_prefix}_{timestamp}.pdf"
        )
    except Exception as e:
        logger.error(f"Error PDF: {e}")
        flash("Error al generar el documento.", "danger")
        return redirect(url_for('reports_bp.index'))

# ==============================================================================
# VISTAS (RESTABLECIDAS Y MEJORADAS)
# ==============================================================================

@reports_bp.route('/')
def index():
    company_id, currency_symbol, conversion_rate = get_company_context()
    if not company_id:
        return redirect(url_for('login_bp.login'))

    today = datetime.now()
    start_date = today.replace(day=1, hour=0, minute=0, second=0)

    try:
        raw_sales = db.session.query(func.sum(Sale.total)).filter(
            Sale.company_id == company_id,
            Sale.status == 'COMPLETED',
            Sale.created_at >= start_date
        ).scalar() or 0
        total_sales_month = float(Decimal(str(raw_sales)) / conversion_rate)

        low_stock_count = Product.query.filter(Product.company_id == company_id, Product.stocks <= 5).count()

        # Mejora: joinedload para cargar el usuario de una vez
        recent_closings = CashClosing.query.options(joinedload(CashClosing.user)).filter_by(company_id=company_id)\
            .order_by(CashClosing.closing_date.desc()).limit(8).all()

        chart_data, chart_labels = [], []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            d_start = day.replace(hour=0, minute=0, second=0)
            d_end = day.replace(hour=23, minute=59, second=59)
            
            daily_sum_raw = db.session.query(func.sum(Sale.total)).filter(
                Sale.company_id == company_id,
                Sale.status == 'COMPLETED',
                Sale.created_at.between(d_start, d_end)
            ).scalar() or 0
            
            chart_data.append(float(Decimal(str(daily_sum_raw)) / conversion_rate))
            chart_labels.append(day.strftime('%a %d'))

    except Exception as e:
        logger.error(f"Error Dashboard: {e}")
        total_sales_month, low_stock_count, recent_closings = 0, 0, []
        chart_data, chart_labels = [0]*7, ["N/A"]*7

    return render_template(
        'reports/index.html',
        total_sales_month=total_sales_month,
        currency_symbol=currency_symbol,
        recent_closings=recent_closings,
        low_stock_count=low_stock_count,
        chart_data=chart_data,
        chart_labels=chart_labels,
        now=today
    )

@reports_bp.route('/export/pdf/sales')
def export_sales_pdf():
    company_id, sym, rate = get_company_context()
    if not company_id: return redirect(url_for('login_bp.login'))

    sales = Sale.query.options(joinedload(Sale.client)).filter_by(company_id=company_id, status='COMPLETED')\
        .order_by(Sale.created_at.desc()).all()

    pdf = OrbisPDF()
    pdf.alias_nb_pages()
    pdf.report_type = f"Ventas y Clientes ({sym})"
    pdf.add_page()

    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("helvetica", "B", 9)
    cols = [(30, "Fecha"), (70, "Cliente"), (30, "Metodo"), (30, f"Total {sym}")]
    for w, txt in cols:
        pdf.cell(w, 10, txt, 1, 0, 'C', True)
    pdf.ln()

    pdf.set_font("helvetica", "", 9)
    grand_total = Decimal('0')

    for s in sales:
        val_conv = Decimal(str(s.total or 0)) / rate
        grand_total += val_conv
        client = s.client.name if s.client else "Consumidor Final"

        pdf.cell(30, 8, s.created_at.strftime('%d/%m/%Y'), 1)
        pdf.cell(70, 8, f" {pdf.safe_text(client[:32])}", 1)
        pdf.cell(30, 8, f" {s.payment_method}", 1, 0, 'C')
        pdf.cell(30, 8, f"{float(val_conv):,.2f}", 1, 1, 'R')

    pdf.ln(2)
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(250, 162, 0)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(130, 10, " TOTAL ACUMULADO DEL PERIODO ", 0, 0, 'R', True)
    pdf.cell(30, 10, f" {float(grand_total):,.2f} ", 0, 1, 'R', True)

    return build_pdf_response(pdf, "Auditoria_Ventas")

@reports_bp.route('/export/pdf/cash')
def export_cash_pdf():
    company_id, sym, _ = get_company_context()
    closings = CashClosing.query.options(joinedload(CashClosing.user)).filter_by(company_id=company_id).order_by(CashClosing.closing_date.desc()).all()

    pdf = OrbisPDF()
    pdf.alias_nb_pages()
    pdf.report_type = "Auditoria de Cierres de Caja"
    pdf.add_page()

    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 8)
    
    headers = [("Fecha/Hora", 40), ("Sistema", 40), ("Fisico", 40), ("Diferencia", 35), ("Usuario", 35)]
    for txt, w in headers:
        pdf.cell(w, 10, txt, 1, 0, 'C', True)
    pdf.ln()

    pdf.set_text_color(0)
    pdf.set_font("helvetica", "", 9)

    for c in closings:
        sys_amt = float(c.system_amount or 0)
        real_amt = float(c.reported_amount or 0)
        diff = real_amt - sys_amt
        user = c.user.name if c.user else "Sist."

        pdf.cell(40, 8, c.closing_date.strftime('%d/%m/%y %H:%M'), 1)
        pdf.cell(40, 8, f"{sys_amt:,.2f}", 1, 0, 'R')
        pdf.cell(40, 8, f"{real_amt:,.2f}", 1, 0, 'R')
        
        if abs(diff) > 0.01:
            pdf.set_text_color(200, 0, 0)
            diff_text = f"{diff:,.2f}"
        else:
            pdf.set_text_color(0, 150, 0)
            diff_text = "OK"
            
        pdf.cell(35, 8, diff_text, 1, 0, 'R')
        pdf.set_text_color(0)
        pdf.cell(35, 8, f" {pdf.safe_text(user[:15])}", 1, 1)

    return build_pdf_response(pdf, "Auditoria_Cajas")

@reports_bp.route('/export/csv')
def export_csv():
    company_id, sym, rate = get_company_context()
    sales = Sale.query.options(joinedload(Sale.client)).filter_by(company_id=company_id).all()

    def generate():
        yield '\ufeffID_VENTA,FECHA,CLIENTE,MONEDA,TOTAL_ORIGINAL,TOTAL_CONVERTIDO,ESTADO\n'
        for s in sales:
            client = s.client.name if s.client else "Consumidor Final"
            val_conv = float(Decimal(str(s.total or 0)) / rate)
            yield f"{s.id},{s.created_at},{client},{sym},{s.total},{val_conv},{s.status}\n"

    return Response(generate(), mimetype='text/csv', 
                    headers={"Content-Disposition": "attachment;filename=data_export_orbis.csv"})

@reports_bp.route('/monthly-history')
def monthly_history():
    company_id, currency_symbol, rate = get_company_context()
    if not company_id: return redirect(url_for('login_bp.login'))

    month_format = func.to_char(Sale.created_at, 'YYYY-MM').label('month')
    query = db.session.query(
        month_format,
        User.name.label('seller_name'),
        func.sum(Sale.total).label('revenue'),
        func.count(Sale.id).label('transactions')
    ).join(User, Sale.user_id == User.id).filter(
        Sale.company_id == company_id,
        Sale.status == 'COMPLETED'
    ).group_by('month', User.name).order_by('month')

    results = query.all()
    return render_template('reports/monthly_history.html', results=results, sym=currency_symbol, rate=rate)

@reports_bp.route('/inventory-health')
def inventory_health():
    company_id, _, _ = get_company_context()
    products = Product.query.filter_by(company_id=company_id).all()
    total_value = sum((p.stocks * (p.purchase_price or 0)) for p in products)
    return render_template('reports/inventory_health.html', products=products, total_value=total_value)

@reports_bp.route('/closings-history')
def closings_history():
    company_id, currency_symbol, rate = get_company_context()
    if not company_id: return redirect(url_for('login_bp.login'))

    closings = CashClosing.query.options(joinedload(CashClosing.user)).filter_by(company_id=company_id)\
        .order_by(CashClosing.closing_date.desc()).all()

    return render_template(
        'reports/closings_history.html', 
        closings=closings, 
        currency_symbol=currency_symbol, 
        conversion_rate=rate
    )