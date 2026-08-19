import os
import sys
from pathlib import Path


# Keep imports stable whether tests run as `pytest` or `python -m pytest`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/orbiserp_test')
os.environ.setdefault('AUTO_CREATE_SCHEMA', '0')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-that-is-long-enough-for-tests')
os.environ.setdefault('APP_ENV', 'testing')
