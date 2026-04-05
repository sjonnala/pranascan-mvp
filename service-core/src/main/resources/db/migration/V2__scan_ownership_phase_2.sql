CREATE TABLE core.scan_sessions (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    user_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    device_model VARCHAR(128),
    app_version VARCHAR(32),
    completed_at TIMESTAMPTZ,
    CONSTRAINT fk_scan_sessions_user
        FOREIGN KEY (user_id) REFERENCES core.users (id)
);

CREATE INDEX idx_scan_sessions_user_id ON core.scan_sessions (user_id);
CREATE INDEX idx_scan_sessions_status ON core.scan_sessions (status);

CREATE TABLE core.scan_results (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    session_id UUID NOT NULL,
    user_id UUID NOT NULL,
    hr_bpm DOUBLE PRECISION,
    hrv_ms DOUBLE PRECISION,
    respiratory_rate DOUBLE PRECISION,
    voice_jitter_pct DOUBLE PRECISION,
    voice_shimmer_pct DOUBLE PRECISION,
    quality_score DOUBLE PRECISION NOT NULL,
    lighting_score DOUBLE PRECISION,
    motion_score DOUBLE PRECISION,
    face_confidence DOUBLE PRECISION,
    audio_snr_db DOUBLE PRECISION,
    trend_alert VARCHAR(64),
    vascular_age_estimate DOUBLE PRECISION,
    vascular_age_confidence DOUBLE PRECISION,
    hb_proxy_score DOUBLE PRECISION,
    anemia_wellness_label VARCHAR(32),
    anemia_confidence DOUBLE PRECISION,
    CONSTRAINT fk_scan_results_session
        FOREIGN KEY (session_id) REFERENCES core.scan_sessions (id),
    CONSTRAINT fk_scan_results_user
        FOREIGN KEY (user_id) REFERENCES core.users (id),
    CONSTRAINT uk_scan_results_session_id UNIQUE (session_id)
);

CREATE INDEX idx_scan_results_user_id ON core.scan_results (user_id);

CREATE TABLE core.scan_result_flags (
    scan_result_id UUID NOT NULL,
    flag_order INTEGER NOT NULL,
    flag VARCHAR(64) NOT NULL,
    CONSTRAINT pk_scan_result_flags PRIMARY KEY (scan_result_id, flag_order),
    CONSTRAINT fk_scan_result_flags_result
        FOREIGN KEY (scan_result_id) REFERENCES core.scan_results (id)
);

CREATE TABLE core.scan_result_warnings (
    scan_result_id UUID NOT NULL,
    warning_order INTEGER NOT NULL,
    warning VARCHAR(64) NOT NULL,
    CONSTRAINT pk_scan_result_warnings PRIMARY KEY (scan_result_id, warning_order),
    CONSTRAINT fk_scan_result_warnings_result
        FOREIGN KEY (scan_result_id) REFERENCES core.scan_results (id)
);
