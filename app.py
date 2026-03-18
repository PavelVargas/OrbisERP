from flask import Flask, session, redirect, url_for, render_template, request, jsonify
from db import db
import os
from datetime import datetime, timedelta
from flask_mail import Mail
from itsdangerous import URLSafeTimedSerializer

# MODELS 
from models.user.user import User
from models.divisas.divisas import ExchangeRate 
from models.company.company import Company # Importado aquí para el middleware

# BLUEPRINTS
from routes.registro.registro import registrar_bp
from routes.dashboard.dashboard import dashboard_bp
from routes.users.users import users_bp
from routes.login.login import login_bp
from routes.products.products import products_bp
from routes.categories.category import category_bp
from routes.stock.stock import stock_bp
from routes.purchase.purchase import purchase_bp
from routes.sales import sales_bp
from routes.client.client import client_bp
from routes.supplier.supplier import supplier_bp
from routes.movements.movements import movements_bp
from routes.transfer_routes.transfer_routes import transfer_bp
from routes.warehouse.warehouse import warehouse_bp
from routes.company.company import company_bp
from routes.perfil.perfil import perfil_bp
from routes.crm.crm import crm_bp
from routes.cash.cash import cash_bp
from routes.super_admin.superadmin import superadmin_bp
from routes.reports.reports import reports_bp
from routes.divisas.divisas import divisas_bp

app = Flask(__name__)

# CONFIGURACIÓN BASE
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/db_inventario"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = 'clave_secreta_orbis_erp_2026'

# --- CONFIGURACIÓN DE CORREO GMAIL ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'pavelvargas1233@gmail.com'
app.config['MAIL_PASSWORD'] = 'bjwp mjha xjra viop' 
app.config['MAIL_DEFAULT_SENDER'] = 'pavelvargas1233@gmail.com'

mail = Mail(app)
s = URLSafeTimedSerializer(app.secret_key)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# INIT DB
db.init_app(app)

# CREAR TABLAS
with app.app_context():
    db.create_all()

# REGISTRAR BLUEPRINTS
app.register_blueprint(registrar_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(users_bp)
app.register_blueprint(login_bp)
app.register_blueprint(products_bp)
app.register_blueprint(category_bp)
app.register_blueprint(stock_bp)
app.register_blueprint(purchase_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(client_bp)
app.register_blueprint(supplier_bp)
app.register_blueprint(movements_bp)
app.register_blueprint(transfer_bp)
app.register_blueprint(warehouse_bp)
app.register_blueprint(company_bp)
app.register_blueprint(perfil_bp)
app.register_blueprint(crm_bp)
app.register_blueprint(superadmin_bp)
app.register_blueprint(cash_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(divisas_bp)

# --- LÓGICA MULTIMONEDA GLOBAL Y PERSISTENTE ---

@app.route('/set-currency/<iso_code>')
def set_currency(iso_code):
    """Cambia la divisa y la guarda permanentemente en la DB para el usuario"""
    user_id = session.get('user_id')
    iso_code = iso_code.upper()
    session['selected_currency'] = iso_code
    
    exchange = ExchangeRate.query.filter_by(currency_code=iso_code).first()
    if exchange:
        session['currency_symbol'] = exchange.symbol
    
    if user_id:
        user = User.query.get(user_id)
        if user:
            user.default_currency = iso_code
            db.session.commit()
            
    return redirect(request.referrer or url_for('dashboard_bp.dashboard'))

@app.route('/api/get-current-rate/<currency>')
def get_api_rate(currency):
    """Endpoint para obtener tasas en tiempo real"""
    try:
        rate = ExchangeRate.get_rate(currency.upper())
        return jsonify({'status': 'success', 'rate': rate})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- MIDDLEWARES Y CONTEXTOS ---

@app.route('/')
def index():
    user_id = session.get('user_id')
    user = User.query.get(user_id) if user_id else None
    return render_template('Home/index.html', user=user)



@app.before_request
def check_company_status():
    """Middleware centralizado de protección de suscripción"""
    
    # 1. Rutas exentas (Nunca se bloquean)
    exempt_routes = [
        'login_bp.login', 'login_bp.logout', 'login_bp.forgot_password', 
        'users_bp.reset_with_token', 'static', 'superadmin_bp', 
        'company_bp.upload_receipt', 'set_currency', 'index'
    ]
    
    # Si la ruta actual es exenta o no tiene endpoint (404), permitir el paso
    if not request.endpoint or any(request.endpoint.startswith(route) for route in exempt_routes):
        return

    # 2. El Superadmin tiene pase libre global (No se le bloquea por suscripción)
    if session.get('user_role') == 'superadmin':
        return

    company_id = session.get('company_id')
    if company_id:
        company = Company.query.get(company_id)
        if company:
            ahora = datetime.utcnow()
         
            tiene_gracia = company.grace_period_until and company.grace_period_until > ahora
            if tiene_gracia:
                return 
            
            ha_vencido = company.expiration_date and company.expiration_date < ahora
            
            if not company.status or ha_vencido:

                return render_template('errors/cuenta_suspendida.html', company=company)

@app.context_processor
def inject_global_data():
    """Inyecta usuario y datos de divisa sincronizados con la DB en todo el HTML"""
    user_id = session.get("user_id")
    user = User.query.get(user_id) if user_id else None
    
    if 'selected_currency' in session:
        currency_code = session['selected_currency']
    elif user and user.default_currency:
        currency_code = user.default_currency
        session['selected_currency'] = currency_code
    else:
        currency_code = 'DOP'

    exchange_info = ExchangeRate.query.filter_by(currency_code=currency_code).first()
    all_currencies = ExchangeRate.query.all()
    
    return dict(
        user=user,
        all_currencies=all_currencies,
        current_currency=currency_code,
        currency_symbol=exchange_info.symbol if exchange_info else 'RD$',
        conversion_rate=float(exchange_info.rate) if exchange_info else 1.0
    )

if __name__ == '__main__':
    # Ejecución del servidor
    app.run(debug=True, host='0.0.0.0', port=5001)