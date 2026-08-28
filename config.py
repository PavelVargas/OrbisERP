import os
from datetime import timedelta
from pathlib import Path

from schema_identity import discover_alembic_head

try:
    from dotenv import load_dotenv
except ImportError:  # Allows a clear configuration error before dependencies are refreshed.
    def load_dotenv(_path):
        return False


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')


def _database_url():
    url = (os.getenv('DATABASE_URL') or '').strip()
    if not url:
        host = os.getenv('POSTGRES_HOST', 'localhost')
        port = os.getenv('POSTGRES_PORT', '5432')
        name = os.getenv('POSTGRES_DB', 'db_inventario')
        user = os.getenv('POSTGRES_USER', 'postgres')
        password = os.getenv('POSTGRES_PASSWORD', '')
        if not password:
            raise RuntimeError(
                'Falta DATABASE_URL o POSTGRES_PASSWORD. Copia .env.example a .env y configura PostgreSQL.'
            )
        url = f'postgresql+psycopg://{user}:{password}@{host}:{port}/{name}'
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    if not url.startswith('postgresql+psycopg://'):
        raise RuntimeError('OrbisERP solo admite PostgreSQL mediante psycopg.')
    return url


class Config:
    ENVIRONMENT = os.getenv('APP_ENV', 'development').lower()
    SECRET_KEY = os.getenv('SECRET_KEY', '')
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').strip().rstrip('/')
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '300')),
        'pool_size': int(os.getenv('DB_POOL_SIZE', '10')),
        'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '20')),
        'pool_timeout': int(os.getenv('DB_POOL_TIMEOUT', '10')),
        'connect_args': {
            'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', '5')),
            'options': f"-c statement_timeout={int(os.getenv('DB_STATEMENT_TIMEOUT_MS', '60000'))}",
        },
    }
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.getenv('COOKIE_SECURE', '1' if ENVIRONMENT == 'production' else '0') == '1'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv('SESSION_HOURS', '12')))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_UPLOAD_MB', '50')) * 1024 * 1024
    TRUST_PROXY = os.getenv('TRUST_PROXY', '0') == '1'
    AUTO_CREATE_SCHEMA = os.getenv('AUTO_CREATE_SCHEMA', '1' if ENVIRONMENT == 'development' else '0') == '1'
    STORAGE_ROOT = os.getenv('STORAGE_ROOT', str(BASE_DIR / 'storage'))
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', '1') == '1'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER') or MAIL_USERNAME
    BILLING_WEBHOOK_SECRET = os.getenv('BILLING_WEBHOOK_SECRET', '')
    BILLING_MODE = os.getenv('BILLING_MODE', 'manual').lower()
    PLAN_BASIC_PRICE_USD = os.getenv('PLAN_BASIC_PRICE_USD', '29').strip()
    PLAN_PRO_PRICE_USD = os.getenv('PLAN_PRO_PRICE_USD', '69').strip()
    PLAN_ULTRA_PRICE_USD = os.getenv('PLAN_ULTRA_PRICE_USD', '149').strip()
    FREECURRENCY_API_KEY = os.getenv('FREECURRENCY_API_KEY', '')
    RATE_LIMIT_STORAGE = os.getenv('RATE_LIMIT_STORAGE', 'database')
    CRON_SECRET = os.getenv('CRON_SECRET', '')
    FISCAL_MODE = os.getenv('FISCAL_MODE', 'disabled').lower()
    EXPECTED_SCHEMA_REVISION = discover_alembic_head(BASE_DIR)
    RELEASE_VERSION = os.getenv('RELEASE_VERSION', (BASE_DIR / 'VERSION').read_text(encoding='utf-8').strip() if (BASE_DIR / 'VERSION').is_file() else 'dev')
    REQUIRE_EMAIL_VERIFICATION = os.getenv('REQUIRE_EMAIL_VERIFICATION', '1' if ENVIRONMENT == 'production' else '0') == '1'
    PUBLIC_REGISTRATION = os.getenv('PUBLIC_REGISTRATION', '0' if ENVIRONMENT == 'production' else '1') == '1'
    TERMS_URL = os.getenv('TERMS_URL', '').strip()
    PRIVACY_URL = os.getenv('PRIVACY_URL', '').strip()
    LEGAL_VERSION = os.getenv('LEGAL_VERSION', 'draft').strip()[:40]
    VERIFY_EMAIL_MAX_AGE_HOURS = int(os.getenv('VERIFY_EMAIL_MAX_AGE_HOURS', '24'))
    VERIFY_EMAIL_CODE_MINUTES = int(os.getenv('VERIFY_EMAIL_CODE_MINUTES', '10'))
    VERIFY_EMAIL_MAX_ATTEMPTS = int(os.getenv('VERIFY_EMAIL_MAX_ATTEMPTS', '5'))
    BACKUP_MAX_AGE_HOURS = int(os.getenv('BACKUP_MAX_AGE_HOURS', '30'))
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    LOG_JSON = os.getenv('LOG_JSON', '0') == '1'
    ERROR_WEBHOOK_URL = os.getenv('ERROR_WEBHOOK_URL', '').strip()
    ERROR_WEBHOOK_SECRET = os.getenv('ERROR_WEBHOOK_SECRET', '').strip()
    BACKUP_STATUS_FILE = os.getenv('BACKUP_STATUS_FILE', str(BASE_DIR / 'backups' / '.last-success'))

    @classmethod
    def validate(cls):
        if cls.FISCAL_MODE not in {'disabled'}:
            raise RuntimeError('FISCAL_MODE debe permanecer en disabled hasta integrar facturación fiscal certificada.')
        if cls.BILLING_MODE not in {'manual', 'webhook'}:
            raise RuntimeError('BILLING_MODE debe ser manual o webhook.')
        if cls.RATE_LIMIT_STORAGE not in {'database', 'memory'}:
            raise RuntimeError('RATE_LIMIT_STORAGE debe ser database o memory.')
        if cls.ENVIRONMENT == 'production':
            if os.getenv('FLASK_DEBUG', '0') == '1' or os.getenv('FLASK_ENV', '').lower() == 'development':
                raise RuntimeError('FLASK_DEBUG/FLASK_ENV de desarrollo no pueden estar activos en producción.')
            storage_path = Path(cls.STORAGE_ROOT).resolve()
            public_static = (BASE_DIR / 'static').resolve()
            if storage_path == public_static or public_static in storage_path.parents:
                raise RuntimeError('STORAGE_ROOT privado no puede estar dentro de static en producción.')
            if len(cls.SECRET_KEY) < 32:
                raise RuntimeError('SECRET_KEY debe tener al menos 32 caracteres en producción.')
            if not cls.PUBLIC_BASE_URL.startswith('https://'):
                raise RuntimeError('PUBLIC_BASE_URL debe usar HTTPS en producción.')
            if not cls.SESSION_COOKIE_SECURE:
                raise RuntimeError('COOKIE_SECURE=1 es obligatorio en producción.')
            if not cls.TRUST_PROXY:
                raise RuntimeError('TRUST_PROXY=1 es obligatorio con el despliegue de producción detrás del proxy TLS.')
            if cls.AUTO_CREATE_SCHEMA:
                raise RuntimeError('AUTO_CREATE_SCHEMA debe estar desactivado en producción; usa Alembic.')
            if cls.RATE_LIMIT_STORAGE != 'database':
                raise RuntimeError('RATE_LIMIT_STORAGE=database es obligatorio en producción.')
            if cls.BILLING_MODE == 'webhook' and len(cls.BILLING_WEBHOOK_SECRET) < 32:
                raise RuntimeError('BILLING_WEBHOOK_SECRET debe tener al menos 32 caracteres en modo webhook.')
            if cls.ERROR_WEBHOOK_URL:
                if not cls.ERROR_WEBHOOK_URL.startswith('https://'):
                    raise RuntimeError('ERROR_WEBHOOK_URL debe usar HTTPS en producción.')
                if len(cls.ERROR_WEBHOOK_SECRET) < 32:
                    raise RuntimeError('ERROR_WEBHOOK_SECRET debe tener al menos 32 caracteres cuando ERROR_WEBHOOK_URL está activo.')
            if len(cls.CRON_SECRET) < 32:
                raise RuntimeError('CRON_SECRET debe tener al menos 32 caracteres en producción.')
            if not cls.MAIL_USERNAME or not cls.MAIL_PASSWORD or not cls.MAIL_DEFAULT_SENDER:
                raise RuntimeError('Configura MAIL_USERNAME, MAIL_PASSWORD y MAIL_DEFAULT_SENDER en producción.')
            if not cls.MAIL_USE_TLS:
                raise RuntimeError('MAIL_USE_TLS=1 es obligatorio en esta configuración de producción.')
            if not cls.REQUIRE_EMAIL_VERIFICATION:
                raise RuntimeError('REQUIRE_EMAIL_VERIFICATION=1 es obligatorio en producción.')
            if cls.PUBLIC_REGISTRATION:
                if not cls.TERMS_URL.startswith('https://') or not cls.PRIVACY_URL.startswith('https://'):
                    raise RuntimeError('Con PUBLIC_REGISTRATION=1 debes configurar TERMS_URL y PRIVACY_URL con HTTPS.')
                if not cls.LEGAL_VERSION or cls.LEGAL_VERSION.lower() == 'draft':
                    raise RuntimeError('Define LEGAL_VERSION con la versión legal publicada antes de abrir el registro.')
