CREATE TABLE measurements (
    measurement_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    reading_id TEXT NOT NULL,
    parameter TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL,
    quality TEXT NOT NULL CHECK (quality IN ('good', 'valid')),
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    UNIQUE (patient_id, device_id, parameter, reading_id)
);
CREATE INDEX measurements_patient_time ON measurements (patient_id, timestamp, measurement_id);
CREATE INDEX measurements_parameter_time ON measurements (patient_id, parameter, timestamp);
CREATE TABLE measurement_receipts (
    message_id TEXT PRIMARY KEY,
    measurement_id TEXT NOT NULL REFERENCES measurements (measurement_id)
);

CREATE TABLE alerts (
    alert_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RESOLVED')),
    timestamp TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    occurrences INTEGER NOT NULL CHECK (occurrences >= 1),
    payload JSONB NOT NULL,
    CHECK (last_seen_at >= timestamp),
    CHECK ((status = 'ACTIVE' AND resolved_at IS NULL) OR
           (status = 'RESOLVED' AND resolved_at >= last_seen_at))
);
CREATE UNIQUE INDEX alerts_one_active_rule ON alerts (patient_id, rule_id) WHERE status = 'ACTIVE';
CREATE INDEX alerts_patient_time ON alerts (patient_id, timestamp, alert_id);

CREATE TABLE technical_events (
    event_id TEXT PRIMARY KEY,
    patient_id TEXT,
    device_id TEXT,
    type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RECORDED', 'ACTIVE', 'RESOLVED')),
    timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX events_patient_time ON technical_events (patient_id, timestamp, event_id);
