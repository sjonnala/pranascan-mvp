ALTER TABLE core.scan_sessions
    ADD COLUMN scan_type VARCHAR(32) NOT NULL DEFAULT 'STANDARD';

UPDATE core.scan_sessions
SET scan_type = 'STANDARD'
WHERE scan_type IS NULL;

ALTER TABLE core.scan_results
    ADD COLUMN stiffness_index DOUBLE PRECISION;
