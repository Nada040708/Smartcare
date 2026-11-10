CREATE TABLE encryption_metadata (
    name TEXT PRIMARY KEY,
    payload JSONB NOT NULL
);
-- The duplicate clear numeric column is no longer used. The encrypted payload is authoritative.
ALTER TABLE measurements DROP COLUMN value;
CREATE TABLE patient_consents (
    patient_id TEXT PRIMARY KEY,
    consent_id UUID NOT NULL,
    granted BOOLEAN NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    changed_by UUID REFERENCES users(user_id)
);
