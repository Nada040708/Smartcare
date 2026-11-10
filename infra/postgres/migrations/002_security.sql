CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('ADMIN', 'DOCTOR', 'NURSE')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX auth_sessions_user ON auth_sessions(user_id);
CREATE TABLE auth_throttle (
    bucket TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE audit_logs (
    log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID REFERENCES users(user_id),
    action TEXT NOT NULL,
    target TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_logs_recent ON audit_logs(timestamp DESC, log_id DESC);
