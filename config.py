import os
from datetime import timedelta
from pathlib import Path

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
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', '300')),
        'pool_size': int(os.getenv('DB_POOL_SIZE', '10')),
        'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '20')),
    }
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.getenv('COOKIE_SECURE', '1' if ENVIRONMENT == 'production' else '0') == '1'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv('SESSION_HOURS', '12')))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_UPLOAD_MB', '10')) * 1024 * 1024
    TRUST_PROXY = os.getenv('TRUST_PROXY', '0') == '1'
    AUTO_CREATE_SCHEMA = os.getenv('AUTO_CREATE_SCHEMA', '1' if ENVIRONMENT == 'development' else '0') == '1'
    STORAGE_ROOT = os.getenv('STORAGE_ROOT', str(BASE_DIR / 'static' / 'uploads'))
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', '1') == '1'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER') or MAIL_USERNAME
    BILLING_WEBHOOK_SECRET = os.getenv('BILLING_WEBHOOK_SECRET', '')
    FISCAL_MODE = os.getenv('FISCAL_MODE', 'disabled').lower()

    @classmethod
    def validate(cls):
        if cls.FISCAL_MODE not in {'disabled'}:
            raise RuntimeError('FISCAL_MODE debe permanecer en disabled hasta integrar facturación fiscal certificada.')
        if cls.ENVIRONMENT == 'production':
            if len(cls.SECRET_KEY) < 32:
                raise RuntimeError('SECRET_KEY debe tener al menos 32 caracteres en producción.')
            if not cls.SESSION_COOKIE_SECURE:
                raise RuntimeError('COOKIE_SECURE=1 es obligatorio en producción.')
            if cls.AUTO_CREATE_SCHEMA:
                raise RuntimeError('AUTO_CREATE_SCHEMA debe estar desactivado en producción; usa Alembic.')
