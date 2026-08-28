import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from schema_identity import discover_alembic_head


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Requiere PostgreSQL de pruebas explícito')
def test_postgresql_connection_and_transaction():
    url = os.environ['TEST_DATABASE_URL']
    assert url.startswith(('postgresql://', 'postgresql+psycopg://'))
    with create_engine(url).begin() as connection:
        assert connection.execute(text('SELECT 1')).scalar_one() == 1


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Requiere PostgreSQL de pruebas explícito')
def test_postgresql_schema_is_at_expected_migration_head():
    url = os.environ['TEST_DATABASE_URL']
    with create_engine(url).connect() as connection:
        revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        assert revision == discover_alembic_head(Path(__file__).resolve().parents[1])
        tables = set(connection.execute(text(
            "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'"
        )).scalars())
        assert {'users', 'companies', 'sales', 'purchase_orders', 'security_attempts', 'cash_sessions', 'sales_taxes', 'notification_rules', 'document_folders'} <= tables
        user_columns = set(connection.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users'"
        )).scalars())
        assert {'avatar_path', 'email_verified_at', 'email_verification_sent_at', 'terms_accepted_at', 'legal_version'} <= user_columns
