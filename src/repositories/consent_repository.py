"""Database decisions override explicit simulation consent in the patient registry."""
from datetime import datetime, timezone
from uuid import uuid4

from src.security.authentication import AuditLog, AuthenticationService


class ConsentRequired(ValueError):
    pass


class ConsentRepository:
    def __init__(self, store):
        self.store = store

    def lock(self, patient_id, *, shared=True):
        function = 'pg_advisory_xact_lock_shared' if shared else 'pg_advisory_xact_lock'
        self.store.connection.execute(f'SELECT {function}(hashtext(%s))',
                                      (f'{self.store.schema}:consent:{patient_id}',))

    def get(self, patient_id, patient=None):
        row = self.store.connection.execute('SELECT * FROM patient_consents WHERE patient_id=%s', (patient_id,)).fetchone()
        if row:
            return {'patient_id':patient_id, 'consent_id':str(row['consent_id']), 'granted':row['granted'],
                    'date':row['changed_at'].isoformat(), 'source':'recorded'}
        consent = patient.consent if patient else None
        return {'patient_id':patient_id, 'consent_id':consent.consent_id if consent else None,
                'granted':bool(consent and consent.granted), 'date':consent.date.isoformat() if consent else None,
                'source':'simulation_config' if consent else 'not_recorded'}

    def set(self, patient_id, granted, actor):
        if not isinstance(granted, bool):
            raise ValueError('Consent must be boolean')
        with self.store.transaction():
            AuthenticationService._lock(self.store)
            AuthenticationService._assert_admin(self.store.connection, actor)
            self.lock(patient_id, shared=False)
            self.store.connection.execute('''INSERT INTO patient_consents VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (patient_id) DO UPDATE SET consent_id=EXCLUDED.consent_id,granted=EXCLUDED.granted,
                changed_at=EXCLUDED.changed_at,changed_by=EXCLUDED.changed_by''',
                (patient_id,uuid4(),granted,datetime.now(timezone.utc),actor['user_id']))
            AuditLog.record(self.store.connection,'CONSENT_GRANTED' if granted else 'CONSENT_REVOKED',actor['user_id'],patient_id)
            return self.get(patient_id)
