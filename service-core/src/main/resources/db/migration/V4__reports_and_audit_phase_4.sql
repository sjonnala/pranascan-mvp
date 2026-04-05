CREATE TABLE core.vitality_reports (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    scan_count INTEGER NOT NULL,
    alert_count INTEGER NOT NULL,
    avg_hr_bpm DOUBLE PRECISION,
    avg_hrv_ms DOUBLE PRECISION,
    avg_respiratory_rate DOUBLE PRECISION,
    avg_voice_jitter_pct DOUBLE PRECISION,
    avg_voice_shimmer_pct DOUBLE PRECISION,
    delta_hr_bpm DOUBLE PRECISION,
    delta_hrv_ms DOUBLE PRECISION,
    latest_vascular_age_estimate DOUBLE PRECISION,
    latest_vascular_age_confidence DOUBLE PRECISION,
    latest_anemia_label VARCHAR(32),
    latest_anemia_confidence DOUBLE PRECISION,
    summary_text TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_vitality_reports_user
        FOREIGN KEY (user_id) REFERENCES core.users (id)
);

CREATE INDEX idx_vitality_reports_user_id ON core.vitality_reports (user_id);
CREATE INDEX idx_vitality_reports_generated_at ON core.vitality_reports (generated_at);

CREATE TABLE core.audit_logs (
    id UUID PRIMARY KEY,
    user_id UUID,
    action VARCHAR(128) NOT NULL,
    resource_type VARCHAR(64),
    resource_id VARCHAR(64),
    http_method VARCHAR(8) NOT NULL,
    http_path VARCHAR(512) NOT NULL,
    http_status INTEGER,
    duration_ms INTEGER,
    ip_address VARCHAR(64),
    user_agent VARCHAR(512),
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_audit_logs_user
        FOREIGN KEY (user_id) REFERENCES core.users (id)
);

CREATE INDEX idx_audit_logs_user_id ON core.audit_logs (user_id);
CREATE INDEX idx_audit_logs_action ON core.audit_logs (action);
CREATE INDEX idx_audit_logs_created_at ON core.audit_logs (created_at);
