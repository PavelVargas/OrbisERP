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

class OrbisPDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        self.company_name = "OrbisERP Cloud"
        self.report_type = "Reporte General"

    def header(self):
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


@reports_bp.route('/')
def index():
    # 1. Forzar limpieza de la caché de SQLAlchemy
    db.session.expire_all()
    
    company_id, currency_symbol, conversion_rate = get_company_context()
    if not company_id:
        return redirect(url_for('login_bp.login'))

    conv_rate = Decimal(str(conversion_rate)) if conversion_rate else Decimal('1.0')
    today = datetime.now()
    
    # Valores por defecto para evitar caídas en cascada
    total_sales_month = 0.0
    low_stock_count = 0
    recent_closings = []
    chart_data = [0]*7
    chart_labels = []

    # ==========================================
    # BLOQUE 1: INGRESO MENSUAL (Filtrado por Mes/Año truncado)
    # ==========================================
    try:
        current_year = today.year
        current_month = today.month

        raw_sales = db.session.query(func.sum(Sale.total)).filter(
            Sale.company_id == company_id,
            Sale.status == 'COMPLETED',
            extract('year', Sale.created_at) == current_year,
            extract('month', Sale.created_at) == current_month
        ).scalar() or Decimal('0.00')
        
        total_sales_month = float(raw_sales / conv_rate)
    except Exception as e:
        logger.error(f"❌ Error calculando ingresos mensuales: {e}")

    # ==========================================
    # BLOQUE 2: ALERTAS DE STOCK (Consulta sobre existencias reales en almacén)
    # ==========================================
    try:
        # Importamos dinámicamente el modelo de existencias por almacén si no está arriba
        from models.warehouse_stock.warehouse_stock import WarehouseStock
        
        # Contamos cuántos productos tienen existencias bajas (<= 5) en cualquiera de tus almacenes
        low_stock_count = db.session.query(func.count(func.distinct(WarehouseStock.product_id))).filter(
            WarehouseStock.company_id == company_id,
            WarehouseStock.quantity <= 5
        ).scalar() or 0
    except Exception as e:
        logger.error(f"❌ Error calculando alertas de stock: {e}")
        # Si falla el método por almacén, usamos el fallback de la tabla de productos
        try:
            low_stock_count = Product.query.filter(Product.company_id == company_id, Product.stocks <= 5).count()
        except : low_stock_count = 0

    # ==========================================
    # BLOQUE 3: ÚLTIMO CIERRE DE CAJA
    # ==========================================
    try:
        recent_closings = CashClosing.query.options(joinedload(CashClosing.user))\
            .filter_by(company_id=company_id)\
            .order_by(CashClosing.closing_date.desc())\
            .limit(5).all()
    except Exception as e:
        logger.error(f"❌ Error consultando cierres de caja: {e}")

    # ==========================================
    # BLOQUE 4: DATOS GRÁFICO (Últimos 7 días ignorando horas con CAST a DATE)
    # ==========================================
    try:
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            target_date = day.date() # Obtenemos solo YYYY-MM-DD
            
            # Comparamos usando la función cast/date de la base de datos para evitar problemas de huso horario
            daily_sum = db.session.query(func.sum(Sale.total)).filter(
                Sale.company_id == company_id,
                Sale.status == 'COMPLETED',
                func.cast(Sale.created_at, db.Date) == target_date
            ).scalar() or Decimal('0.00')
            
            chart_data.append(float(daily_sum / conv_rate))
            chart_labels.append(day.strftime('%a %d'))
    except Exception as e:
        logger.error(f"❌ Error generando gráfico lineal: {e}")
        chart_data = [0]*7
        chart_labels = ["N/A"]*7

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
@reports_bp.route('/export/print/sales')
def export_sales_print():
    company_id, sym, rate = get_company_context()
    if not company_id: 
        return redirect(url_for('login_bp.login'))
        
    sales = Sale.query.options(joinedload(Sale.client))\
        .filter_by(company_id=company_id, status='COMPLETED')\
        .order_by(Sale.created_at.desc()).all()
        
    grand_total = Decimal('0')
    processed_sales = []
    
    for s in sales:
        val_conv = Decimal(str(s.total or 0)) / rate
        grand_total += val_conv
        processed_sales.append({
            'date': s.created_at,
            'client': s.client.name if s.client else "Consumidor Final",
            'payment_method': s.payment_method,
            'total_converted': val_conv
        })
        
    return render_template(
        'reports/print_sales.html',
        sales=processed_sales,
        grand_total=grand_total,
        currency_symbol=sym,
        gen_date=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        company_id=company_id
    )

@reports_bp.route('/export/print/cash')
def export_cash_print():
    company_id, sym, _ = get_company_context()
    if not company_id: 
        return redirect(url_for('login_bp.login'))
        
    closings = CashClosing.query.options(joinedload(CashClosing.user))\
        .filter_by(company_id=company_id)\
        .order_by(CashClosing.closing_date.desc()).all()
        
    return render_template(
        'reports/print_cash.html',
        closings=closings,
        currency_symbol=sym,
        gen_date=datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        company_id=company_id
    )
    
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
    return Response(generate(), mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=data_export_orbis.csv"})

@reports_bp.route('/monthly-history')
def monthly_history():
    company_id, currency_symbol, rate = get_company_context()
    if not company_id: return redirect(url_for('login_bp.login'))
    month_format = func.to_char(Sale.created_at, 'YYYY-MM').label('month')
    query = db.session.query(month_format, User.name.label('seller_name'), func.sum(Sale.total).label('revenue'), func.count(Sale.id).label('transactions')).join(User, Sale.user_id == User.id).filter(Sale.company_id == company_id, Sale.status == 'COMPLETED').group_by('month', User.name).order_by('month')
    results = query.all()
    return render_template('reports/monthly_history.html', results=results, sym=currency_symbol, rate=rate)

@reports_bp.route('/inventory-health')
def inventory_health():
    company_id, currency_symbol, _ = get_company_context()
    if not company_id:
        return redirect(url_for('login_bp.login'))
        
    products = Product.query.filter_by(company_id=company_id).all()
    
    # Importamos el modelo de stock por almacén para hacer la consulta limpia
    from models.warehouse_stock.warehouse_stock import WarehouseStock
    
    total_value = Decimal('0.00')
    for p in products:
        # 1. Obtener el costo de forma segura
        cost = getattr(p, 'purchase_price', None) or getattr(p, 'cost', None) or Decimal('0.00')
        if not isinstance(cost, Decimal):
            cost = Decimal(str(cost))

        # 2. SOLUCIÓN: Sumar explícitamente la columna .quantity filtrando por el ID del producto
        stock_qty = db.session.query(
            func.coalesce(func.sum(WarehouseStock.quantity), 0)
        ).filter(
            WarehouseStock.product_id == p.id,
            WarehouseStock.company_id == company_id
        ).scalar() or 0

        # Guardamos el entero en el objeto para el HTML
        p.calculated_stock = int(stock_qty)
        
        # Calcular valor total acumulado del almacén
        total_value += (Decimal(str(p.calculated_stock)) * cost)
        
    return render_template(
        'reports/inventory_health.html', 
        products=products, 
        total_value=float(total_value),
        currency_symbol=currency_symbol
    )
    
@reports_bp.route('/closings-history')
def closings_history():
    company_id, currency_symbol, rate = get_company_context()
    if not company_id: return redirect(url_for('login_bp.login'))
    closings = CashClosing.query.options(joinedload(CashClosing.user)).filter_by(company_id=company_id).order_by(CashClosing.closing_date.desc()).all()
    return render_template('reports/closings_history.html', closings=closings, currency_symbol=currency_symbol, conversion_rate=rate)