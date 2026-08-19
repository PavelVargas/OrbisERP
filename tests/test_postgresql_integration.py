import os

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Requiere PostgreSQL de pruebas explícito')
def test_postgresql_connection_and_transaction():
    url = os.environ['TEST_DATABASE_URL']
    assert url.startswith(('postgresql://', 'postgresql+psycopg://'))
    with create_engine(url).begin() as connection:
        assert connection.execute(text('SELECT 1')).scalar_one() == 1
