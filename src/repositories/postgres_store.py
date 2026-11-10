"""PostgreSQL connection and versioned schema; no implicit fallback to memory."""
import os
from pathlib import Path
import re

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from dotenv import load_dotenv
from psycopg.types.json import Jsonb
from src.security.encryption import EncryptionService

ROOT = Path(__file__).resolve().parents[2]


class PostgresStore:
    def __init__(self, dsn=None, *, schema='smartcare', initialize=True):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
            raise ValueError('Invalid PostgreSQL schema name')
        load_dotenv(ROOT / '.env', override=False)
        self.encryption = None
        self.schema = schema
        self._writer_locked = False
        dsn = dsn or os.getenv('DATABASE_URL')
        password = os.getenv('POSTGRES_PASSWORD')
        if not dsn and not password:
            raise ValueError('POSTGRES_PASSWORD must be set in the private .env file')
        settings = {} if dsn else dict(
            host=os.getenv('POSTGRES_HOST', '127.0.0.1'),
            port=os.getenv('POSTGRES_PORT', '5433'),
            user=os.getenv('POSTGRES_USER', 'smartcare'),
            password=password,
            dbname=os.getenv('POSTGRES_DB', 'smartcare'),
        )
        self.connection = psycopg.connect(dsn or '', **settings, autocommit=True,
                                          connect_timeout=5, row_factory=dict_row)
        try:
            self.connection.execute("SET TIME ZONE 'UTC'")
            self.connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            if not initialize:
                return
            with self.transaction():
                self.connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (f'{schema}:migrations',))
                self.connection.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema)))
                self.connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                self.connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)')
                versions = [row['version'] for row in self.connection.execute('SELECT version FROM schema_migrations')]
                if any(version not in (1, 2, 3, 4, 5) for version in versions):
                    raise ValueError('Unsupported database schema version')
                for version, name in [(1, '001_initial.sql'), (2, '002_security.sql'), (3, '003_connections.sql')]:
                    if version not in versions:
                        migration = ROOT / 'infra/postgres/migrations' / name
                        self.connection.execute(migration.read_text())
                        self.connection.execute('INSERT INTO schema_migrations VALUES (%s)', (version,))
                if 4 not in versions:
                    locked = self.connection.execute('SELECT pg_try_advisory_xact_lock(hashtext(%s)) AS ok',
                        (f'{schema}:monitoring_writer',)).fetchone()['ok']
                    if not locked:
                        raise RuntimeError('Stop the monitoring writer before the privacy migration')
                    self.encryption = EncryptionService.from_file()
                    for table, identity in [('measurements','measurement_id'),('alerts','alert_id')]:
                        rows = self.connection.execute(sql.SQL('SELECT {},payload FROM {}').format(sql.Identifier(identity),sql.Identifier(table))).fetchall()
                        for row in rows:
                            self.connection.execute(sql.SQL('UPDATE {} SET payload=%s WHERE {}=%s').format(sql.Identifier(table),sql.Identifier(identity)),
                                (Jsonb(self.encode_payload(table,row['payload'])),row[identity]))
                    self.connection.execute((ROOT/'infra/postgres/migrations/004_privacy.sql').read_text())
                    self.connection.execute('INSERT INTO encryption_metadata VALUES (%s,%s)',
                        ('key_check',Jsonb(self.encode_payload('key_check',{'schema':schema}))))
                    self.connection.execute('INSERT INTO schema_migrations VALUES (4)')
                if 5 not in versions:
                    self.connection.execute((ROOT/'infra/postgres/migrations/005_clinical_workflows.sql').read_text())
                    self.connection.execute('INSERT INTO schema_migrations VALUES (5)')
                self._verify_key()
        except BaseException:
            self.close()
            raise

    def _verify_key(self):
        if self.encryption is None:
            self.encryption = EncryptionService.from_file()
        row = self.connection.execute("SELECT payload FROM encryption_metadata WHERE name='key_check'").fetchone()
        if not row or self.decode_payload('key_check',row['payload']) != {'schema':self.schema}:
            raise RuntimeError('Invalid encryption metadata')

    def encode_payload(self, table, payload):
        if self.encryption is None:
            self._verify_key()
        return self.encryption.encrypt(payload, f'{self.schema}:{table}')

    def decode_payload(self, table, payload, identity=None):
        if self.encryption is None:
            self._verify_key()
        field = {'measurements':'measurement_id','alerts':'alert_id'}.get(table) if identity is not None else None
        return self.encryption.decrypt(payload, f'{self.schema}:{table}', identity=identity, identity_field=field)

    def transaction(self):
        return self.connection.transaction()

    def acquire_writer(self):
        """One stateful monitoring session per schema; repositories remain readable."""
        if self._writer_locked:
            raise RuntimeError('This store already has a monitoring session')
        row = self.connection.execute('SELECT pg_try_advisory_lock(hashtext(%s)) AS acquired',
                                      (f'{self.schema}:monitoring_writer',)).fetchone()
        if not row['acquired']:
            raise RuntimeError('Another monitoring session is already using this schema')
        self._writer_locked = True

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
