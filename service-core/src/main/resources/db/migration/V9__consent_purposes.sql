-- V9: purpose-scoped DPDP consent (T-401/T-403). Ledger stays append-only; legacy rows are
-- tagged 'legacy.bundled', never rewritten in meaning. Current INSERTs keep working.
ALTER TABLE core.consent_records
    ADD COLUMN purpose_id VARCHAR(48),
    ADD COLUMN notice_version VARCHAR(32),
    ADD COLUMN notice_language VARCHAR(16),
    ADD COLUMN notice_sha256 CHAR(64),
    ADD COLUMN age_attested_18plus BOOLEAN,
    ADD COLUMN capture_channel VARCHAR(16),
    ADD COLUMN app_version VARCHAR(32),
    ADD COLUMN prev_consent_id UUID REFERENCES core.consent_records (id);

UPDATE core.consent_records SET purpose_id = 'legacy.bundled' WHERE purpose_id IS NULL;

CREATE INDEX idx_consent_records_user_purpose_created
    ON core.consent_records (user_id, purpose_id, created_at DESC);
