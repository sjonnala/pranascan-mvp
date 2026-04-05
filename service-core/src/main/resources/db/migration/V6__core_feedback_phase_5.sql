CREATE TABLE core.scan_feedback
(
    id              UUID PRIMARY KEY,
    session_id      UUID         NOT NULL,
    user_id         UUID         NOT NULL,
    useful_response VARCHAR(16)  NOT NULL,
    nps_score       INTEGER,
    comment         VARCHAR(500),
    created_at      TIMESTAMPTZ  NOT NULL,
    updated_at      TIMESTAMPTZ  NOT NULL,
    CONSTRAINT uk_scan_feedback_session_id UNIQUE (session_id),
    CONSTRAINT fk_scan_feedback_session_id FOREIGN KEY (session_id) REFERENCES core.scan_sessions (id),
    CONSTRAINT fk_scan_feedback_user_id FOREIGN KEY (user_id) REFERENCES core.users (id),
    CONSTRAINT chk_scan_feedback_useful_response CHECK (useful_response IN ('useful', 'needs_work')),
    CONSTRAINT chk_scan_feedback_nps_score CHECK (nps_score IS NULL OR (nps_score >= 0 AND nps_score <= 10))
);

CREATE INDEX idx_scan_feedback_user_id ON core.scan_feedback (user_id);
