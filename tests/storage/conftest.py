from uuid import uuid4

import pytest
from psycopg import sql

from src.repositories.postgres_store import PostgresStore


@pytest.fixture
def postgres_schema():
    schema = 'smartcare_test_' + uuid4().hex
    try:
        yield schema
    finally:
        # Only this test's generated schema is removed; never the application data.
        with PostgresStore(schema=schema) as cleanup:
            cleanup.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
