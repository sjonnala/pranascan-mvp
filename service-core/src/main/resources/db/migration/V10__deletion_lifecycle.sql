-- V10: DPDP deletion lifecycle (T-401/T-403). Keeps legacy `status` (PENDING/COMPLETED/FAILED)
-- for the current code; `state` carries the runbook's state machine. No purge worker yet.
ALTER TABLE core.deletion_requests
    ADD COLUMN state VARCHAR(24),
    ADD COLUMN scope VARCHAR(32),
    ADD COLUMN trigger_source VARCHAR(32),
    ADD COLUMN target_at TIMESTAMPTZ,
    ADD COLUMN sla_due_at TIMESTAMPTZ,
    ADD COLUMN completed_at TIMESTAMPTZ,
    ADD COLUMN legal_hold_reason VARCHAR(256),
    ADD COLUMN verified_by VARCHAR(128);

UPDATE core.deletion_requests SET
    state = CASE status WHEN 'COMPLETED' THEN 'COMPLETED'
                        WHEN 'FAILED' THEN 'IN_PROGRESS'
                        ELSE 'RECEIVED' END,
    scope = 'ACCOUNT_ALL',
    trigger_source = 'USER_REQUEST',
    target_at = created_at + INTERVAL '30 days',
    sla_due_at = created_at + INTERVAL '90 days',
    completed_at = CASE WHEN status = 'COMPLETED' THEN purged_at END
WHERE state IS NULL;

ALTER TABLE core.deletion_requests
    ADD CONSTRAINT ck_deletion_requests_state CHECK (state IS NULL OR state IN
        ('RECEIVED','VERIFIED','NOTICE_SENT','IN_PROGRESS','PRIMARY_PURGED','BACKUPS_EXPIRING',
         'COMPLETED','REJECTED','ON_HOLD_LEGAL'));

CREATE INDEX idx_deletion_requests_state_target ON core.deletion_requests (state, target_at);

CREATE TABLE core.deletion_audit (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    deletion_request_id UUID NOT NULL REFERENCES core.deletion_requests (id),
    from_state VARCHAR(24),
    to_state VARCHAR(24) NOT NULL,
    store VARCHAR(48),
    rows_affected BIGINT,
    actor VARCHAR(128) NOT NULL,
    note VARCHAR(512)
);
CREATE INDEX idx_deletion_audit_request ON core.deletion_audit (deletion_request_id, created_at);
