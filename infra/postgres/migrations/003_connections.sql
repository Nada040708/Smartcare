CREATE TABLE device_connections (
    patient_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (patient_id, device_id)
);
CREATE INDEX events_active_technical ON technical_events(patient_id, type) WHERE status='ACTIVE';
