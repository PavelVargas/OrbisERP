from flask import Flask, session, redirect, url_for, render_template, request, jsonify, abort, flash
from db import db
import os
from datetime import datetime, timezone
from flask_mail import Mail
from itsdangerous import URLSafeTimedSerializer
from flask_migrate import Migrate
from sqlalchemy import inspect, text
# MODELS 
from models.user.user import User
from models.divisas.divisas import ExchangeRate 
from models.company.company import Company
from models.company.company import GlobalAnnouncement
from permissions import required_permissions

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
from routes.launchpad.launchpad import launchpad_bp

app = Flask(__name__)

# =========================
# 🐘 POSTGRESQL (LOCAL + DATABASE_URL EN PRODUCCIÓN)
# =========================
LOCAL_POSTGRES_URL = "postgresql+psycopg://postgres:pavel@localhost:5432/db_inventario"
DATABASE_URL = (os.getenv("DATABASE_URL") or LOCAL_POSTGRES_URL).strip()

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

if not DATABASE_URL.startswith("postgresql+psycopg://"):
    raise RuntimeError("OrbisERP requiere una conexión PostgreSQL válida.")

if os.getenv("DATABASE_URL"):
    print("🐘 PostgreSQL configurado mediante DATABASE_URL")
else:
    print("🐘 PostgreSQL local: db_inventario")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.secret_key = os.getenv("SECRET_KEY") or os.urandom(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '1' if os.getenv('RAILWAY_ENVIRONMENT') else '0') == '1',
    MAX_CONTENT_LENGTH=int(os.getenv('MAX_UPLOAD_MB', '10')) * 1024 * 1024,
)

# =========================
# 📧 MAIL CONFIG
# =========================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME", "tuemail@gmail.com")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD", "password")
app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']

mail = Mail(app)
s = URLSafeTimedSerializer(app.secret_key)

# =========================
# 📁 UPLOADS
# =========================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# INIT DB
db.init_app(app)

migrate = Migrate(app, db)

def create_superadmin():
    admin_email = os.getenv('SUPERADMIN_EMAIL')
    admin_password = os.getenv('SUPERADMIN_PASSWORD')
    if not admin_email or not admin_password:
        return
    try:
        admin = User.query.filter_by(email=admin_email.lower()).first()
        
        if not admin:
            new_admin = User(
                name='Administrador Global',
                email=admin_email.lower(),
                password='pending-hash',
                cedula='000-0000000-0',
                role='superadmin',
                default_currency='DOP',
                company_id=None,
                warehouse_id=None
            )
            new_admin.set_password(admin_password)
            
            db.session.add(new_admin)
            db.session.commit()
            
            print("🔥 Superadmin creado automáticamente")
        else:
            print("✅ Superadmin ya existe")

    except Exception as e:
        print("⚠️ Error creando superadmin:", e)


def ensure_schema_compatibility():
    """Apply tiny, idempotent compatibility fixes for existing installations.

    Alembic remains the migration source of truth. These guards cover legacy
    installations that relied on db.create_all(), which creates missing tables
    but cannot alter columns in existing PostgreSQL tables.
    """
    engine = db.engine
    if engine.dialect.name != 'postgresql':
        return

    schema = inspect(engine)
    table_names = set(schema.get_table_names())

    if 'users' in table_names:
        user_columns = {column['name']: column for column in schema.get_columns('users')}
        password_column = user_columns.get('password')
        password_length = getattr(password_column['type'], 'length', None) if password_column else None
        if password_column and password_length is not None and password_length < 255:
            with engine.begin() as connection:
                connection.execute(text(
                    'ALTER TABLE users ALTER COLUMN password TYPE VARCHAR(255)'
                ))
            print('✅ PostgreSQL actualizado: users.password ampliado a 255 caracteres')
        if 'permissions' not in user_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE users ADD COLUMN permissions TEXT'))
            print('✅ PostgreSQL actualizado: users.permissions agregado')

    if 'products' in table_names:
        product_columns = {column['name'] for column in schema.get_columns('products')}
        if 'image_path' not in product_columns:
            with engine.begin() as connection:
                connection.execute(text(
                    'ALTER TABLE products ADD COLUMN image_path VARCHAR(255)'
                ))
            print('✅ PostgreSQL actualizado: products.image_path agregado')

    if 'stock_transfers' in table_names:
        transfer_columns = {column['name'] for column in schema.get_columns('stock_transfers')}
        with engine.begin() as connection:
            if 'from_location_id' not in transfer_columns:
                connection.execute(text(
                    'ALTER TABLE stock_transfers ADD COLUMN from_location_id INTEGER '
                    'REFERENCES warehouse_locations(id)'
                ))
                print('✅ PostgreSQL actualizado: stock_transfers.from_location_id agregado')
            if 'to_location_id' not in transfer_columns:
                connection.execute(text(
                    'ALTER TABLE stock_transfers ADD COLUMN to_location_id INTEGER '
                    'REFERENCES warehouse_locations(id)'
                ))
                print('✅ PostgreSQL actualizado: stock_transfers.to_location_id agregado')

    if 'purchase_orders' in table_names:
        order_columns = {column['name'] for column in schema.get_columns('purchase_orders')}
        with engine.begin() as connection:
            if 'subtotal' not in order_columns:
                connection.execute(text('ALTER TABLE purchase_orders ADD COLUMN subtotal NUMERIC(12, 2) DEFAULT 0'))
                connection.execute(text('UPDATE purchase_orders SET subtotal = COALESCE(total_cost, 0)'))
                print('✅ PostgreSQL actualizado: purchase_orders.subtotal agregado')
            if 'tax_total' not in order_columns:
                connection.execute(text('ALTER TABLE purchase_orders ADD COLUMN tax_total NUMERIC(12, 2) DEFAULT 0'))
                print('✅ PostgreSQL actualizado: purchase_orders.tax_total agregado')

    if 'purchase_order_items' in table_names:
        item_columns = {column['name'] for column in schema.get_columns('purchase_order_items')}
        with engine.begin() as connection:
            if 'tax_name' not in item_columns:
                connection.execute(text("ALTER TABLE purchase_order_items ADD COLUMN tax_name VARCHAR(80) DEFAULT 'Exento' NOT NULL"))
                print('✅ PostgreSQL actualizado: purchase_order_items.tax_name agregado')
            if 'tax_rate' not in item_columns:
                connection.execute(text('ALTER TABLE purchase_order_items ADD COLUMN tax_rate NUMERIC(5, 2) DEFAULT 0 NOT NULL'))
                print('✅ PostgreSQL actualizado: purchase_order_items.tax_rate agregado')
            if 'tax_included' not in item_columns:
                connection.execute(text('ALTER TABLE purchase_order_items ADD COLUMN tax_included BOOLEAN DEFAULT FALSE NOT NULL'))
                print('✅ PostgreSQL actualizado: purchase_order_items.tax_included agregado')

try:
    with app.app_context():
        db.create_all()
        ensure_schema_compatibility()
        create_superadmin()
        print("✅ DB lista")
except Exception as e:
    print("⚠️ DB error:", e)

# =========================
# REGISTER BLUEPRINTS
# =========================
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
app.register_blueprint(launchpad_bp)

# =========================
# ROUTES
# =========================

@app.context_processor
def inject_global_announcements():
    # Buscamos si hay algún anuncio activo en la DB
    active = GlobalAnnouncement.query.filter_by(is_active=True).first()
    return dict(active_announcement=active)

@app.route('/')
def index():
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    return render_template('Home/index.html', user=user)

@app.route('/set-currency/<iso_code>')
def set_currency(iso_code):
    user_id = session.get('user_id')
    iso_code = iso_code.upper()
    session['selected_currency'] = iso_code
    
    exchange = ExchangeRate.query.filter_by(currency_code=iso_code).first()
    if exchange:
        session['currency_symbol'] = exchange.symbol
    
    if user_id:
        user = db.session.get(User, user_id)
        if user:
            user.default_currency = iso_code
            db.session.commit()
            
    return redirect(request.referrer or url_for('dashboard_bp.dashboard'))

@app.before_request
def enforce_request_security():
    """Central authentication, same-origin and read-only enforcement."""
    public_endpoints = {
        'index', 'login_bp.login', 'login_bp.logout',
        'login_bp.forgot_password', 'registrar.register',
        'users_bp.reset_with_token', 'static'
    }
    endpoint = request.endpoint or ''

    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        origin = request.headers.get('Origin')
        referer = request.headers.get('Referer')
        expected = request.host_url.rstrip('/')
        if origin and origin.rstrip('/') != expected:
            abort(403)
        if not origin and referer and not referer.startswith(request.host_url):
            abort(403)

    if endpoint not in public_endpoints and not endpoint.startswith('static'):
        if not session.get('user_id'):
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'error': 'Autenticación requerida'}), 401
            return redirect(url_for('login_bp.login', next=request.full_path))

    if endpoint not in public_endpoints and not endpoint.startswith('superadmin_bp.'):
        current_user = db.session.get(User, session.get('user_id'))
        required = required_permissions(endpoint, request.method)
        if required and (not current_user or not current_user.has_any_permission(*required)):
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'error': 'No tienes permiso para esta operación', 'required': list(required)}), 403
            return render_template('errors/permission_denied.html', user=current_user, required=required), 403

    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and session.get('company_id'):
        company = db.session.get(Company, session['company_id'])
        allowed = {'company_bp.upload_receipt', 'login_bp.logout'}
        if company and company.is_readonly and endpoint not in allowed and session.get('user_role') != 'superadmin':
            if request.is_json:
                return jsonify({'error': 'La empresa está en modo solo lectura'}), 403
            flash('La empresa está en modo solo lectura.', 'warning')
            return redirect(request.referrer or url_for('dashboard_bp.dashboard'))


@app.before_request
def check_company_status():
    exempt_routes = [
        'login_bp.login','login_bp.logout','static','set_currency','index'
    ]

    if not request.endpoint or any(request.endpoint.startswith(route) for route in exempt_routes):
        return

    if session.get('user_role') == 'superadmin':
        return

    company_id = session.get('company_id')
    if company_id:
        company = db.session.get(Company, company_id)
        if company:
            ahora = datetime.now(timezone.utc).replace(tzinfo=None)

            tiene_gracia = company.grace_period_until and company.grace_period_until > ahora
            if tiene_gracia:
                return

            ha_vencido = company.expiration_date and company.expiration_date < ahora

            if not company.status or ha_vencido:
                return render_template('errors/cuenta_suspendida.html', company=company)

@app.context_processor
def inject_global_data():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    
    currency_code = session.get('selected_currency','DOP')

    exchange_info = ExchangeRate.query.filter_by(currency_code=currency_code).first()
    all_currencies = ExchangeRate.query.all()
    
    return dict(
        user=user,
        can=(lambda permission: bool(user and user.has_permission(permission))),
        all_currencies=all_currencies,
        current_currency=currency_code,
        currency_symbol=exchange_info.symbol if exchange_info else 'RD$',
        conversion_rate=float(exchange_info.rate) if exchange_info else 1.0
    )


@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    if request.path.startswith('/api/'):
        response.headers.setdefault('Cache-Control', 'no-store')
    return response


@app.errorhandler(403)
def forbidden(_error):
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'error': 'Acceso denegado'}), 403
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    return render_template('errors/permission_denied.html', user=user, required=()), 403


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({'error': 'El archivo supera el límite permitido.'}), 413

# =========================
# RUN
# =========================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG') == '1')
