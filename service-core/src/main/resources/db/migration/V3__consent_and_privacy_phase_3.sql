CREATE TABLE core.consent_records (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    user_id UUID NOT NULL,
    action VARCHAR(32) NOT NULL,
    consent_version VARCHAR(16) NOT NULL,
    purpose VARCHAR(256) NOT NULL,
    ip_address VARCHAR(64),
    user_agent VARCHAR(512),
    deletion_scheduled_at TIMESTAMPTZ,
    CONSTRAINT fk_consent_records_user
        FOREIGN KEY (user_id) REFERENCES core.users (id)
);

CREATE INDEX idx_consent_records_user_id ON core.consent_records (user_id);
CREATE INDEX idx_consent_records_action ON core.consent_records (action);

CREATE TABLE core.deletion_requests (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    user_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    purged_at TIMESTAMPTZ,
    failure_reason VARCHAR(512),
    CONSTRAINT fk_deletion_requests_user
        FOREIGN KEY (user_id) REFERENCES core.users (id)
);

CREATE INDEX idx_deletion_requests_user_id ON core.deletion_requests (user_id);
CREATE INDEX idx_deletion_requests_status ON core.deletion_requests (status);
