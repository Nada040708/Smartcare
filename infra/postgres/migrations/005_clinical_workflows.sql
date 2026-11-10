-- Workflows visible in the clinical web application.
ALTER TABLE users
    ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'APPROVED'
        CHECK (approval_status IN ('PENDING', 'APPROVED')),
    ADD COLUMN requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN approved_at TIMESTAMPTZ;

UPDATE users SET approved_at=created_at WHERE approval_status='APPROVED';

CREATE TABLE patient_registry (
    patient_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    profiles TEXT[] NOT NULL,
    monitoring_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (patient_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    CHECK (cardinality(profiles) BETWEEN 1 AND 3),
    CHECK (profiles <@ ARRAY['diabetes','hypertension','anxiety']::TEXT[])
);

CREATE TABLE alert_actions (
    action_id UUID PRIMARY KEY,
    alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
    actor_id UUID NOT NULL REFERENCES users(user_id),
    action TEXT NOT NULL CHECK (action IN ('RESOLVED', 'DOCTOR_CONTACTED')),
    target_user_id UUID REFERENCES users(user_id),
    note TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX alert_actions_alert_time ON alert_actions(alert_id, timestamp DESC);
