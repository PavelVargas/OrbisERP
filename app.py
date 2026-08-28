from services.numeric import NumericValueError
from services.validation import BusinessRuleError
from services.time_utils import utcnow
from flask import Flask, session, redirect, url_for, render_template, request, jsonify, abort, flash, g, has_request_context
from flask.logging import default_handler
from db import db
import os
import sys
from datetime import datetime, timedelta, timezone
from flask_mail import Mail
from itsdangerous import URLSafeTimedSerializer
from flask_migrate import Migrate
from sqlalchemy import inspect, text
from logging.handlers import RotatingFileHandler
from pathlib import Path
import logging
import json
import smtplib
import hashlib
import hmac
import threading
import click
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import BadRequest
from config import Config
from security import hash_session_token, init_security, password_error
# MODELS 
from models.user.user import User
from models.divisas.divisas import ExchangeRate 
from models.company.company import Company
from models.company.company import GlobalAnnouncement
from models.backoffice import AppNotification
from models.auditoria.auditoria import AuditLog
from models.operations import UserSession, OperationJob, SecurityAttempt, RequestIdempotency
from models.productivity import CashSession, CompanyDocument, NotificationRule, Promotion, SalesTax
from models.retail import CompanyRetailSettings, Branch, PosTerminal, UnitOfMeasure, ProductVariant, PriceList, ApiKey
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
from routes.operations import operations_bp
from routes.backoffice import backoffice_bp
from routes.governance import governance_bp
from routes.workspace import workspace_bp
from routes.retail import retail_bp
from routes.api_v1 import api_v1_bp

app = Flask(__name__)


def _expects_json_response():
    """Detect API/AJAX clients even when they submit form-encoded payloads."""
    accept = request.headers.get('Accept', '')
    return (
        request.path.startswith('/api/')
        or request.is_json
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in accept
    )


@app.errorhandler(NumericValueError)
@app.errorhandler(BusinessRuleError)
def _handle_business_rule_error(error):
    """Convert safe domain/input validation failures into HTTP 400 responses."""
    db.session.rollback()
    app.logger.info("Rejected business input: %s", error)
    description = str(error) or "Revisa los datos ingresados."
    if _expects_json_response():
        return jsonify(error=description, request_id=getattr(g, 'request_id', None)), 400
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    bad_request = BadRequest(description=description)
    return render_template(
        'errors/request_error.html',
        user=user,
        error=bad_request,
        request_id=getattr(g, 'request_id', None),
    ), 400

app.config.from_object(Config)
Config.validate()
if app.config['TRUST_PROXY']:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.permanent_session_lifetime = app.config['PERMANENT_SESSION_LIFETIME']
init_security(app)

class _JsonLogFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


log_dir = Path(os.getenv('LOG_DIR', Path(__file__).resolve().parent / 'logs'))
log_dir.mkdir(parents=True, exist_ok=True)
log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'), logging.INFO)
log_formatter = _JsonLogFormatter() if app.config.get('LOG_JSON') else logging.Formatter(
    '%(asctime)s %(levelname)s %(name)s %(message)s'
)
file_handler = RotatingFileHandler(log_dir / 'orbiserp.log', maxBytes=5_000_000, backupCount=5)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(log_level)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(log_level)
if default_handler in app.logger.handlers:
    app.logger.removeHandler(default_handler)
if not any(getattr(existing, '_orbiserp_handler', False) for existing in app.logger.handlers):
    file_handler._orbiserp_handler = True
    stream_handler._orbiserp_handler = True
    app.logger.addHandler(file_handler)
    app.logger.addHandler(stream_handler)
app.logger.setLevel(log_level)
app.logger.propagate = False
app.logger.info('PostgreSQL configurado; release=%s env=%s', app.config['RELEASE_VERSION'], app.config['ENVIRONMENT'])

# =========================
# 📧 MAIL CONFIG
# =========================
mail = Mail(app)
s = URLSafeTimedSerializer(app.secret_key)

# INIT DB
db.init_app(app)

migrate = Migrate(app, db)

def create_superadmin():
    admin_email = os.getenv('SUPERADMIN_EMAIL')
    admin_password = os.getenv('SUPERADMIN_PASSWORD')
    if not admin_email or not admin_password:
        return
    issue = password_error(admin_password)
    if issue:
        raise RuntimeError(f'SUPERADMIN_PASSWORD inválida: {issue}')
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
                warehouse_id=None,
                email_verified_at=utcnow(),
            )
            new_admin.set_password(admin_password)
            
            db.session.add(new_admin)
            db.session.commit()
            
            print("🔥 Superadmin creado automáticamente")
        else:
            print("✅ Superadmin ya existe")

    except Exception:
        db.session.rollback()
        raise


@app.cli.command('create-superadmin')
def create_superadmin_command():
    """Create the first superadmin from environment variables."""
    if not os.getenv('SUPERADMIN_EMAIL') or not os.getenv('SUPERADMIN_PASSWORD'):
        raise RuntimeError('Configura SUPERADMIN_EMAIL y SUPERADMIN_PASSWORD antes de ejecutar el comando.')
    create_superadmin()


@app.cli.command('check-production')
def check_production_command():
    """Validate configuration and the PostgreSQL connection."""
    Config.validate()
    db.session.execute(text('SELECT 1'))
    revision = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    if revision != app.config['EXPECTED_SCHEMA_REVISION']:
        raise click.ClickException(
            f'Esquema desactualizado: {revision}; esperado {app.config["EXPECTED_SCHEMA_REVISION"]}. '
            'Ejecuta flask --app app db upgrade.'
        )
    print('✅ Configuración y PostgreSQL listos para producción')


@app.cli.command('check-integrations')
def check_integrations_command():
    """Verify storage, SMTP configuration and external service readiness."""
    storage = Path(app.config['STORAGE_ROOT'])
    storage.mkdir(parents=True, exist_ok=True)
    probe = storage / '.write-test'
    probe.write_text('ok', encoding='utf-8')
    probe.unlink()
    print('✅ Almacenamiento de archivos escribible')

    if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'], timeout=10) as smtp:
            if app.config['MAIL_USE_TLS']:
                smtp.starttls()
            smtp.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        print('✅ SMTP autenticado correctamente')
    else:
        print('⚠️ SMTP no configurado; recuperación de contraseña no enviará correos')

    if app.config['BILLING_MODE'] == 'webhook':
        print('✅ Cobro configurado en modo webhook firmado')
    else:
        print('ℹ️ Cobro mensual configurado en modo manual')
    print('✅ Integraciones revisadas')


@app.cli.command('maintenance-check')
@click.option('--strict/--no-strict', default=True, help='Devuelve error si una comprobación operativa falla.')
def maintenance_check_command(strict):
    """Run non-destructive operational checks suitable for cron/monitoring."""
    issues = []
    warnings = []
    try:
        db.session.execute(text('SELECT 1'))
        revision = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision != app.config['EXPECTED_SCHEMA_REVISION']:
            issues.append(f'Alembic {revision}; esperado {app.config["EXPECTED_SCHEMA_REVISION"]}')
    except Exception as exc:
        db.session.rollback()
        issues.append(f'PostgreSQL no disponible: {exc.__class__.__name__}')

    storage = Path(app.config['STORAGE_ROOT'])
    try:
        storage.mkdir(parents=True, exist_ok=True)
        probe = storage / '.maintenance-write-test'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
    except Exception as exc:
        issues.append(f'Almacenamiento privado no escribible: {exc.__class__.__name__}')

    backup_status = Path(app.config['BACKUP_STATUS_FILE'])
    if backup_status.exists():
        age_hours = (datetime.now(timezone.utc).timestamp() - backup_status.stat().st_mtime) / 3600
        if age_hours > app.config['BACKUP_MAX_AGE_HOURS']:
            issues.append(f'Último respaldo hace {age_hours:.1f} h; máximo {app.config["BACKUP_MAX_AGE_HOURS"]} h')
    elif app.config['ENVIRONMENT'] == 'production':
        issues.append('No existe evidencia de respaldo (.last-success)')
    else:
        warnings.append('No hay evidencia de respaldo en este entorno')

    try:
        since = utcnow() - timedelta(hours=24)
        failed_jobs = OperationJob.query.filter(OperationJob.status == 'FAILED', OperationJob.created_at >= since).count()
        if failed_jobs:
            warnings.append(f'{failed_jobs} proceso(s) fallido(s) en las últimas 24 h')
        stale_cash = CashSession.query.filter(
            CashSession.status == 'OPEN', CashSession.opened_at < utcnow() - timedelta(hours=24)
        ).count()
        if stale_cash:
            warnings.append(f'{stale_cash} turno(s) de caja llevan más de 24 h abiertos')
    except Exception:
        db.session.rollback()
        warnings.append('No se pudieron revisar procesos/cajas')

    for warning in warnings:
        click.echo(f'⚠️ {warning}')
    if issues:
        for issue in issues:
            click.echo(f'❌ {issue}')
        if strict:
            raise click.ClickException('Mantenimiento requiere atención.')
    else:
        click.echo('✅ Mantenimiento operativo sin bloqueadores')


@app.cli.command('maintenance-clean')
@click.option('--retention-days', default=30, type=click.IntRange(7, 3650), show_default=True)
def maintenance_clean_command(retention_days):
    """Purge ephemeral security/session housekeeping rows; business/audit history is preserved."""
    cutoff = utcnow() - timedelta(days=retention_days)
    session_cutoff = utcnow() - timedelta(days=max(retention_days, 90))
    deleted_attempts = SecurityAttempt.query.filter(SecurityAttempt.attempted_at < cutoff).delete(synchronize_session=False)
    deleted_keys = RequestIdempotency.query.filter(RequestIdempotency.created_at < cutoff).delete(synchronize_session=False)
    deleted_sessions = UserSession.query.filter(
        UserSession.revoked_at.is_not(None), UserSession.revoked_at < session_cutoff
    ).delete(synchronize_session=False)
    db.session.commit()
    click.echo(
        f'✅ Limpieza: intentos={deleted_attempts}, idempotencia={deleted_keys}, sesiones_revocadas={deleted_sessions}'
    )


@app.cli.command('audit-integrity')
def audit_integrity_command():
    """Detect legacy rows that violate the current business invariants."""
    checks = {
        'stock negativo': 'SELECT COUNT(*) FROM warehouse_stock WHERE quantity < 0',
        'líneas de venta no positivas': 'SELECT COUNT(*) FROM sale_items WHERE quantity <= 0 OR price < 0',
        'ventas sin empresa': 'SELECT COUNT(*) FROM sales WHERE company_id IS NULL',
        'traslados no positivos': 'SELECT COUNT(*) FROM stock_transfers WHERE quantity <= 0',
        'abonos no positivos': 'SELECT COUNT(*) FROM customer_payments WHERE amount <= 0',
        'pagos no positivos': 'SELECT COUNT(*) FROM supplier_payments WHERE amount <= 0',
        'gastos no positivos': 'SELECT COUNT(*) FROM expenses WHERE amount <= 0',
    }
    findings = []
    for label, statement in checks.items():
        try:
            count = db.session.execute(text(statement)).scalar_one()
        except Exception:
            db.session.rollback()
            continue  # The optional module/table may not exist in an older installation.
        if count:
            findings.append(f'{label}: {count}')
    if findings:
        raise click.ClickException('Se encontraron inconsistencias:\n- ' + '\n- '.join(findings))
    print('✅ Integridad de inventario, ventas y pagos verificada')


@app.cli.command('validate-integrity')
def validate_integrity_command():
    """Validate hardened PostgreSQL constraints after the legacy audit passes."""
    constraints = {
        'sales': (
            'ck_sales_subtotal_nonnegative', 'ck_sales_itbis_nonnegative',
            'ck_sales_total_nonnegative', 'ck_sales_paid_nonnegative',
            'ck_sales_balance_nonnegative', 'ck_sales_status', 'ck_sales_company_required',
        ),
        'sale_items': ('ck_sale_items_quantity_positive', 'ck_sale_items_price_nonnegative'),
        'warehouse_stock': ('ck_warehouse_stock_quantity_nonnegative',),
        'stock_transfers': ('ck_stock_transfers_quantity_positive', 'ck_stock_transfers_status'),
        'sale_return_items': (
            'ck_sale_return_items_quantity_positive', 'ck_sale_return_items_price_nonnegative',
        ),
        'customer_payments': ('ck_customer_payments_amount_positive',),
        'supplier_bills': ('ck_supplier_bills_amount_positive', 'ck_supplier_bills_paid_range'),
        'supplier_payments': ('ck_supplier_payments_amount_positive',),
        'expenses': ('ck_expenses_amount_positive',),
        'inventory_count_items': (
            'ck_inventory_count_expected_nonnegative', 'ck_inventory_count_counted_nonnegative',
        ),
    }
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    try:
        for table, names in constraints.items():
            if table not in tables:
                continue
            existing = {row.get('name') for row in inspector.get_check_constraints(table)}
            for name in names:
                if name in existing:
                    db.session.execute(text(f'ALTER TABLE {table} VALIDATE CONSTRAINT {name}'))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise click.ClickException(
            'No se pudieron validar todas las restricciones. Ejecuta audit-integrity y corrige los datos heredados.'
        ) from exc
    print('✅ Restricciones PostgreSQL validadas')


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
        if 'is_active' not in user_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL'))
            print('✅ PostgreSQL actualizado: users.is_active agregado')
        if 'session_version' not in user_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE users ADD COLUMN session_version INTEGER DEFAULT 1 NOT NULL'))
            print('✅ PostgreSQL actualizado: users.session_version agregado')
        if 'totp_recovery_codes' not in user_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE users ADD COLUMN totp_recovery_codes TEXT'))
            print('✅ PostgreSQL actualizado: users.totp_recovery_codes agregado')
        if 'email_verified_at' not in user_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP'))
                connection.execute(text('UPDATE users SET email_verified_at = NOW() WHERE email_verified_at IS NULL'))
            print('✅ PostgreSQL actualizado: users.email_verified_at agregado')
        if 'email_verification_sent_at' not in user_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE users ADD COLUMN email_verification_sent_at TIMESTAMP'))
            print('✅ PostgreSQL actualizado: users.email_verification_sent_at agregado')
        if 'terms_accepted_at' not in user_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE users ADD COLUMN terms_accepted_at TIMESTAMP'))
            print('✅ PostgreSQL actualizado: users.terms_accepted_at agregado')
        if 'legal_version' not in user_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE users ADD COLUMN legal_version VARCHAR(40)'))
            print('✅ PostgreSQL actualizado: users.legal_version agregado')

    if 'products' in table_names:
        product_columns = {column['name'] for column in schema.get_columns('products')}
        with engine.begin() as connection:
            if 'image_path' not in product_columns:
                connection.execute(text('ALTER TABLE products ADD COLUMN image_path VARCHAR(255)'))
                print('✅ PostgreSQL actualizado: products.image_path agregado')
            if 'archived_at' not in product_columns:
                connection.execute(text('ALTER TABLE products ADD COLUMN archived_at TIMESTAMP'))
                print('✅ PostgreSQL actualizado: products.archived_at agregado')
            if 'sales_tax_id' not in product_columns:
                connection.execute(text('ALTER TABLE products ADD COLUMN sales_tax_id INTEGER REFERENCES sales_taxes(id)'))
                print('✅ PostgreSQL actualizado: products.sales_tax_id agregado')

    if 'clients' in table_names:
        client_columns = {column['name'] for column in schema.get_columns('clients')}
        if 'archived_at' not in client_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE clients ADD COLUMN archived_at TIMESTAMP'))
            print('✅ PostgreSQL actualizado: clients.archived_at agregado')

    if 'suppliers' in table_names:
        supplier_columns = {column['name'] for column in schema.get_columns('suppliers')}
        if 'archived_at' not in supplier_columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE suppliers ADD COLUMN archived_at TIMESTAMP'))
            print('✅ PostgreSQL actualizado: suppliers.archived_at agregado')

    if 'sales' in table_names:
        sale_columns = {column['name'] for column in schema.get_columns('sales')}
        additions = {
            'quote_valid_until': 'DATE',
            'quote_notes': 'VARCHAR(500)',
            'promotion_id': 'INTEGER REFERENCES promotions(id)',
            'discount_amount': 'NUMERIC(10, 2) DEFAULT 0 NOT NULL',
        }
        with engine.begin() as connection:
            for column, definition in additions.items():
                if column not in sale_columns:
                    connection.execute(text(f'ALTER TABLE sales ADD COLUMN {column} {definition}'))
                    print(f'✅ PostgreSQL actualizado: sales.{column} agregado')

    if 'sale_items' in table_names:
        sale_item_columns = {column['name'] for column in schema.get_columns('sale_items')}
        additions = {
            'tax_name': "VARCHAR(80) DEFAULT 'ITBIS 18%' NOT NULL",
            'tax_rate': 'NUMERIC(5, 2) DEFAULT 18 NOT NULL',
            'tax_included': 'BOOLEAN DEFAULT TRUE NOT NULL',
        }
        with engine.begin() as connection:
            for column, definition in additions.items():
                if column not in sale_item_columns:
                    connection.execute(text(f'ALTER TABLE sale_items ADD COLUMN {column} {definition}'))
                    print(f'✅ PostgreSQL actualizado: sale_items.{column} agregado')

    if 'sales_taxes' in table_names and 'companies' in table_names:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO sales_taxes (company_id, name, rate, price_included, active, is_default, created_at)
                SELECT id, 'ITBIS 18%', 18, TRUE, TRUE, TRUE, NOW()
                FROM companies c
                WHERE NOT EXISTS (SELECT 1 FROM sales_taxes t WHERE t.company_id = c.id)
            """))

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

    if 'companies' in table_names:
        company_columns = {column['name'] for column in schema.get_columns('companies')}
        additions = {
            'billing_provider': 'VARCHAR(40)', 'billing_customer_id': 'VARCHAR(120)',
            'billing_subscription_id': 'VARCHAR(120)',
            'cancel_at_period_end': 'BOOLEAN DEFAULT FALSE NOT NULL',
            'onboarding_completed': 'BOOLEAN DEFAULT FALSE NOT NULL',
        }
        with engine.begin() as connection:
            for column, definition in additions.items():
                if column not in company_columns:
                    connection.execute(text(f'ALTER TABLE companies ADD COLUMN {column} {definition}'))
                    print(f'✅ PostgreSQL actualizado: companies.{column} agregado')

def _is_alembic_command():
    """Avoid runtime schema checks while Flask-Migrate/Alembic is importing app."""
    arguments = {argument.lower() for argument in sys.argv[1:]}
    return 'db' in arguments or 'alembic' in arguments


def _runtime_schema_state():
    """Return the Alembic revision and critical Retail 2.0 schema drift.

    Runtime startup never mutates the business schema. Alembic is the source of
    truth; this guard exists so an old database cannot boot against newer ORM
    models and fail later with confusing UndefinedColumn errors.
    """
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    revision = None
    if 'alembic_version' in tables:
        revision = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar_one_or_none()

    critical = {
        'users': {'branch_id', 'terminal_id'},
        'warehouses': {'branch_id'},
        'sales': {'branch_id', 'terminal_id', 'price_list_id'},
        'products': {'sale_mode', 'tracking', 'image_url'},
    }
    missing = []
    for table, required_columns in critical.items():
        if table not in tables:
            missing.append(f'{table} (tabla)')
            continue
        columns = {column['name'] for column in inspector.get_columns(table)}
        missing.extend(f'{table}.{column}' for column in sorted(required_columns - columns))
    return revision, missing


def require_current_schema():
    expected = app.config['EXPECTED_SCHEMA_REVISION']
    revision, missing = _runtime_schema_state()
    if revision == expected and not missing:
        return

    current = revision or 'sin revisión Alembic'
    details = f" Columnas/tablas faltantes: {', '.join(missing[:8])}." if missing else ''
    raise RuntimeError(
        f'Base de datos desactualizada: revisión actual {current}; esperada {expected}.{details} '
        'Ejecuta: flask --app app db upgrade'
    )


if app.config['AUTO_CREATE_SCHEMA'] and not _is_alembic_command():
    try:
        with app.app_context():
            try:
                require_current_schema()
                ensure_schema_compatibility()
                create_superadmin()
                print(f"✅ DB local lista (schema {app.config['EXPECTED_SCHEMA_REVISION']})")
            except Exception:
                # Flask-SQLAlchemy sessions are application-context scoped.
                # Roll back before leaving the context so startup failures never
                # trigger a secondary "working outside of application context" error.
                db.session.rollback()
                raise
    except Exception as exc:
        app.logger.error('La base de datos no está lista: %s', exc)
        print(f'❌ DB no lista: {exc}')
        print('   Ejecuta: flask --app app db upgrade')
        raise SystemExit(2) from exc

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
app.register_blueprint(operations_bp)
app.register_blueprint(backoffice_bp)
app.register_blueprint(governance_bp)
app.register_blueprint(workspace_bp)
app.register_blueprint(retail_bp)
app.register_blueprint(api_v1_bp)

# =========================
# ROUTES
# =========================

@app.context_processor
def inject_global_announcements():
    # Buscamos si hay algún anuncio activo en la DB
    active = GlobalAnnouncement.query.filter_by(is_active=True).first()
    unread_notifications = 0
    if session.get('company_id') and session.get('user_id'):
        try:
            if session.pop('notifications_dirty', False):
                from services.notification_rules import evaluate_notification_rules
                evaluate_notification_rules(int(session['company_id']))
            from sqlalchemy import or_
            unread_notifications = AppNotification.query.filter(
                AppNotification.company_id == session['company_id'], AppNotification.read_at.is_(None),
                or_(AppNotification.user_id.is_(None), AppNotification.user_id == session['user_id'])
            ).count()
        except Exception:
            db.session.rollback()
            app.logger.exception('No se pudieron actualizar las notificaciones configurables')
    return dict(active_announcement=active, unread_notifications=unread_notifications, tablet_mode_active=bool(getattr(g, 'tablet_mode_active', False) or session.get('tablet_mode')))

@app.route('/')
def index():
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    return render_template('Home/index.html', user=user)

@app.post('/set-currency/<iso_code>')
def set_currency(iso_code):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    iso_code = iso_code.upper()
    exchange = ExchangeRate.query.filter_by(currency_code=iso_code, company_id=company_id).first()
    if not exchange:
        abort(404)
    session['selected_currency'] = iso_code
    session['currency_symbol'] = exchange.symbol
    
    if user_id:
        user = db.session.get(User, user_id)
        if user:
            user.default_currency = iso_code
            db.session.commit()
            
    return redirect(request.referrer or url_for('dashboard_bp.dashboard'))

TABLET_UI_COOKIE = 'orbis_ui_mode'
TABLET_UI_QUERY = '_tablet'
LEGACY_TABLET_COOKIE = 'orbis_tablet_mode'
TABLET_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def _request_has_tablet_signal():
    """Return True when this navigation explicitly belongs to tablet mode.

    Tablet is an application profile, not a property of one template. The
    signed Flask session is authoritative while the query marker and cookies
    are continuity fallbacks for browsers/webviews that can rebuild session UI
    state between navigations. A stale legacy ``0`` cookie never disables an
    already active tablet session; only the explicit desktop route does that.
    """
    if (request.args.get(TABLET_UI_QUERY) or '').strip().lower() in {'1', 'true', 'tablet'}:
        return True
    if (request.cookies.get(TABLET_UI_COOKIE) or '').strip().lower() == 'tablet':
        return True
    legacy_values = request.cookies.getlist(LEGACY_TABLET_COOKIE)
    return '1' in legacy_values


@app.before_request
def sync_tablet_mode_preference():
    """Restore tablet mode before every authenticated screen is rendered."""
    g.tablet_mode_active = False
    if request.endpoint == 'static' or not session.get('user_id'):
        return

    # Session wins. A positive navigation/cookie signal may restore it, but a
    # stale desktop cookie is never allowed to tear it down on the next page.
    if session.get('tablet_mode') or _request_has_tablet_signal():
        if not session.get('tablet_mode'):
            session['tablet_mode'] = True
            session.modified = True
        g.tablet_mode_active = True


@app.url_defaults
def propagate_tablet_mode(endpoint, values):
    """Carry tablet mode through every internal ``url_for`` navigation."""
    if not has_request_context() or not session.get('tablet_mode'):
        return
    if endpoint in {
        'static', 'login_bp.login', 'login_bp.logout',
        'dashboard_bp.disable_tablet_mode', 'launchpad_bp.exit_tablet',
    }:
        return
    values.setdefault(TABLET_UI_QUERY, '1')


@app.after_request
def persist_tablet_mode_preference(response):
    """Refresh the canonical tablet cookie on every tablet response."""
    if session.get('user_id') and session.get('tablet_mode'):
        response.set_cookie(
            TABLET_UI_COOKIE, 'tablet', max_age=TABLET_COOKIE_MAX_AGE, path='/',
            samesite='Lax', secure=request.is_secure, httponly=False,
        )
        # Keep old clients compatible, but legacy ``0`` is never authoritative.
        response.set_cookie(
            LEGACY_TABLET_COOKIE, '1', max_age=TABLET_COOKIE_MAX_AGE, path='/',
            samesite='Lax', secure=request.is_secure, httponly=False,
        )
    return response


@app.before_request
def enforce_request_security():
    """Central authentication, same-origin and read-only enforcement."""
    public_endpoints = {
        'index', 'login_bp.login', 'login_bp.two_factor', 'login_bp.logout',
        'login_bp.forgot_password', 'registrar.register', 'registrar.verification_pending',
        'registrar.verify_email', 'registrar.resend_verification',
        'users_bp.reset_with_token', 'static',
        'operations_bp.health_live', 'operations_bp.health_ready', 'operations_bp.billing_webhook',
        'superadmin_bp.cron_check_expirations'
    }
    endpoint = request.endpoint or ''

    is_external_api = endpoint.startswith('api_v1.')

    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and not is_external_api and endpoint not in {
        'operations_bp.billing_webhook', 'superadmin_bp.cron_check_expirations'
    }:
        origin = request.headers.get('Origin')
        referer = request.headers.get('Referer')
        expected = request.host_url.rstrip('/')
        if origin and origin.rstrip('/') != expected:
            abort(403)
        if not origin and referer and not referer.startswith(request.host_url):
            abort(403)

    if endpoint not in public_endpoints and not endpoint.startswith('static') and not is_external_api:
        if not session.get('user_id'):
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'error': 'Autenticación requerida'}), 401
            return redirect(url_for('login_bp.login', next=request.full_path))

        authenticated_user = db.session.get(User, session.get('user_id'))
        raw_session_token = session.get('server_session_token')
        registered_session = UserSession.query.filter_by(
            session_hash=hash_session_token(raw_session_token),
            user_id=session.get('user_id'),
            revoked_at=None,
        ).first() if raw_session_token else None
        invalid_session = (
            not authenticated_user
            or not authenticated_user.is_active
            or not registered_session
            or int(session.get('session_version') or 0) != int(authenticated_user.session_version or 1)
            or (
                authenticated_user.role != 'superadmin'
                and int(session.get('company_id') or 0) != int(authenticated_user.company_id or 0)
            )
        )
        if invalid_session:
            if registered_session:
                registered_session.revoked_at = utcnow()
                registered_session.revoke_reason = 'Cuenta, empresa o versión de sesión modificada'
                db.session.commit()
            session.clear()
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'error': 'La sesión ya no es válida'}), 401
            flash('Tu sesión cambió o fue revocada. Inicia sesión nuevamente.', 'warning')
            return redirect(url_for('login_bp.login'))

        # Keep non-security-critical cached context synchronized with the user row.
        # This makes role/permission/location edits effective on the next request
        # without forcing a logout/login cycle.
        live_context = {
            'user_name': authenticated_user.name,
            'user_role': authenticated_user.role,
            'company_id': authenticated_user.company_id,
            'warehouse_id': authenticated_user.warehouse_id,
            'branch_id': authenticated_user.branch_id,
            'terminal_id': authenticated_user.terminal_id,
        }
        for key, value in live_context.items():
            if session.get(key) != value:
                if value is None:
                    session.pop(key, None)
                else:
                    session[key] = value

        if registered_session.last_seen_at < utcnow() - timedelta(minutes=5):
            registered_session.last_seen_at = utcnow()
            registered_session.ip_address = (request.remote_addr or '')[:50]
            db.session.commit()

    if endpoint not in public_endpoints and not endpoint.startswith('superadmin_bp.') and not is_external_api:
        current_user = authenticated_user
        required = required_permissions(endpoint, request.method)
        if required and (not current_user or not current_user.has_any_permission(*required)):
            if _expects_json_response():
                return jsonify({'error': 'No tienes permiso para esta operación', 'required': list(required)}), 403
            return render_template('errors/permission_denied.html', user=current_user, required=required), 403

    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and session.get('company_id'):
        company = db.session.get(Company, session['company_id'])
        allowed = {'company_bp.upload_receipt', 'login_bp.logout'}
        if company and company.is_readonly and endpoint not in allowed and session.get('user_role') != 'superadmin':
            if _expects_json_response():
                return jsonify({
                    'error': 'Empresa en modo solo lectura',
                    'detail': 'No se guardó ningún cambio. Un administrador maestro debe reactivar el acceso de escritura para esta empresa.'
                }), 403
            flash('Modo solo lectura: no se guardó ningún cambio. La empresa está bloqueada para escritura; solicita al administrador maestro que reactive el acceso antes de crear, editar, cobrar, recibir o eliminar registros.', 'warning')
            return redirect(request.referrer or url_for('dashboard_bp.dashboard'))


@app.before_request
def check_company_status():
    exempt_routes = [
        'login_bp.login','login_bp.logout','static','set_currency','index'
    ]

    if not request.endpoint or request.endpoint.startswith('api_v1.') or any(request.endpoint.startswith(route) for route in exempt_routes):
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


def _friendly_audit_description(response):
    endpoint = request.endpoint or ''
    method = request.method
    labels = {
        'operations_bp.onboarding': 'Completó o actualizó la configuración inicial de la empresa.',
        'company_bp.settings': 'Actualizó los datos y preferencias de la empresa.',
        'retail_bp.settings_update': 'Actualizó la configuración de Retail avanzado.',
        'workspace_bp.document_upload': 'Subió un archivo al gestor de Documentos.',
        'workspace_bp.document_update': 'Renombró o movió un archivo en Documentos.',
        'workspace_bp.document_delete': 'Movió un archivo a la Papelera.',
        'workspace_bp.restore_document': 'Restauró un archivo desde la Papelera.',
        'workspace_bp.purge_document': 'Eliminó definitivamente un archivo de la Papelera.',
        'login_bp.logout': 'Cerró su sesión de OrbisERP.',
        'backoffice_bp.security_settings': 'Actualizó una opción de seguridad de la cuenta.',
        'workspace_bp.notification_rules': 'Actualizó las reglas automáticas de alertas.',
        'sales_bp.create_sale': 'Registró o actualizó una venta.',
        'client_bp.create_client': 'Creó un nuevo cliente.',
        'supplier_bp.create_supplier': 'Creó un nuevo proveedor.',
        'products_bp.create_product': 'Creó un nuevo producto o servicio.',
    }
    text_value = labels.get(endpoint)
    if not text_value:
        action = endpoint.split('.')[-1].replace('_', ' ').strip() if endpoint else request.path
        text_value = f'{method} · {action[:1].upper() + action[1:] if action else "Actividad registrada"}.'
    route_ids = []
    for key, value in (request.view_args or {}).items():
        if key.endswith('_id') or key == 'id':
            route_ids.append(f'{key.replace("_", " ")} #{value}')
    if route_ids:
        text_value += ' Referencia: ' + ', '.join(route_ids) + '.'
    return f'{text_value} Resultado HTTP {response.status_code}.'[:1000]


@app.after_request
def audit_successful_mutation(response):
    """Record successful state-changing requests without exposing form data."""
    if (
        request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}
        and response.status_code < 400
        and session.get('company_id')
        and session.get('user_id')
        and request.endpoint not in {'operations_bp.billing_webhook'}
    ):
        # Reevaluate configurable alerts once on the next rendered page. This keeps
        # the notification counter current without running the rule engine on every GET.
        session['notifications_dirty'] = True
        try:
            db.session.add(AuditLog(
                company_id=session['company_id'],
                user_id=session['user_id'],
                action=f'HTTP_{request.method}:{request.endpoint}'[:255],
                description=_friendly_audit_description(response),
                ip_address=(request.remote_addr or '')[:50],
                request_id=getattr(g, 'request_id', None), endpoint=request.endpoint,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception('No se pudo registrar la auditoría de la solicitud')
    return response

@app.context_processor
def inject_global_data():
    from services.product_images import product_image_url
    from services.quantity import display_decimal, display_quantity
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    
    currency_code = session.get('selected_currency','DOP')

    company_id = session.get('company_id')
    current_company = db.session.get(Company, company_id) if company_id else None
    exchange_info = ExchangeRate.query.filter_by(currency_code=currency_code, company_id=company_id).first() if company_id else None
    all_currencies = ExchangeRate.query.filter_by(company_id=company_id).order_by(ExchangeRate.currency_code.asc()).all() if company_id else []
    
    return dict(
        user=user,
        current_company=current_company,
        company_readonly=bool(current_company and current_company.is_readonly),
        can=(lambda permission: bool(user and user.has_permission(permission))),
        all_currencies=all_currencies,
        current_currency=currency_code,
        currency_symbol=exchange_info.symbol if exchange_info else 'RD$',
        conversion_rate=float(exchange_info.rate) if exchange_info else 1.0,
        product_image_url=product_image_url,
        display_quantity=display_quantity,
        display_decimal=display_decimal,
    )


@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    if request.path.startswith('/api/'):
        response.headers.setdefault('Cache-Control', 'no-store')
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.endpoint != 'static':
        app.logger.info(
            'audit request_id=%s method=%s path=%s status=%s user_id=%s company_id=%s ip=%s',
            getattr(g, 'request_id', '-'), request.method, request.path, response.status_code,
            session.get('user_id'), session.get('company_id'), request.remote_addr,
        )
    return response


def _dispatch_error_webhook(payload):
    url = app.config.get('ERROR_WEBHOOK_URL')
    if not url:
        return

    def deliver():
        try:
            import requests
            body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            headers = {'Content-Type': 'application/json', 'User-Agent': 'OrbisERP-Incident/1'}
            secret = app.config.get('ERROR_WEBHOOK_SECRET') or ''
            if secret:
                headers['X-Orbis-Signature'] = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            requests.post(url, data=body, headers=headers, timeout=3).raise_for_status()
        except Exception:
            app.logger.exception('No se pudo entregar el webhook de incidente')

    threading.Thread(target=deliver, name='orbiserp-incident-webhook', daemon=True).start()


@app.errorhandler(403)
def forbidden(_error):
    if _expects_json_response():
        return jsonify({'error': 'Acceso denegado', 'request_id': getattr(g, 'request_id', None)}), 403
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    return render_template(
        'errors/permission_denied.html', user=user, required=(),
        request_id=getattr(g, 'request_id', None),
    ), 403


@app.errorhandler(413)
def file_too_large(_error):
    limit_mb = max(1, int(app.config.get('MAX_CONTENT_LENGTH', 0) / (1024 * 1024)))
    message = f'El archivo supera el límite permitido de {limit_mb} MB.'
    if request.path.startswith('/operations/data'):
        flash(message + ' Para importar productos con imágenes, sube el ZIP de catálogo, no el ZIP del código de la aplicación.', 'danger')
        return redirect(url_for('operations_bp.data_center'))
    if _expects_json_response():
        return jsonify({'error': message, 'max_upload_mb': limit_mb, 'request_id': getattr(g, 'request_id', None)}), 413
    flash(message, 'danger')
    return redirect(request.referrer or url_for('dashboard_bp.dashboard'))


@app.errorhandler(400)
@app.errorhandler(409)
@app.errorhandler(429)
def friendly_request_error(error):
    if _expects_json_response():
        return jsonify(error=getattr(error, 'description', 'Solicitud inválida'), request_id=getattr(g, 'request_id', None)), error.code
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    return render_template('errors/request_error.html', user=user, error=error,
                           request_id=getattr(g, 'request_id', None)), error.code


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    request_id = getattr(g, 'request_id', '-')
    app.logger.error('Unhandled request error id=%s', request_id, exc_info=True)
    _dispatch_error_webhook({
        'event': 'http.500', 'request_id': request_id, 'method': request.method,
        'path': request.path, 'endpoint': request.endpoint,
        'company_id': session.get('company_id'), 'user_id': session.get('user_id'),
        'release': app.config.get('RELEASE_VERSION'), 'environment': app.config.get('ENVIRONMENT'),
    })
    if _expects_json_response():
        return jsonify(error='Ocurrió un error interno.', request_id=request_id), 500
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    return render_template('errors/request_error.html', user=user, error=error,
                           request_id=getattr(g, 'request_id', None)), 500

# =========================
# RUN
# =========================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG') == '1')
