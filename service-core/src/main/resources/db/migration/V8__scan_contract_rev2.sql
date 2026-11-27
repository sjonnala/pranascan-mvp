-- V8: persist Cycle-1/2 scan upgrades (scan_intelligence.proto contract revision 2, T-401/T-403).
-- Additive and nullable only; no rewrites of existing columns. Current JPA INSERTs keep working.
ALTER TABLE core.scan_sessions
    ADD COLUMN device_platform VARCHAR(16),
    ADD COLUMN device_os_version VARCHAR(32),
    ADD COLUMN capture_path VARCHAR(16),
    ADD COLUMN color_range VARCHAR(16),
    ADD COLUMN ae_lock VARCHAR(16),
    ADD COLUMN awb_lock VARCHAR(16),
    ADD COLUMN delivered_fps DOUBLE PRECISION,
    ADD COLUMN fps_jitter_ms DOUBLE PRECISION,
    ADD COLUMN mean_frame_interval_ms DOUBLE PRECISION,
    ADD COLUMN frame_timestamp_source VARCHAR(16),
    ADD COLUMN contract_revision SMALLINT;

ALTER TABLE core.scan_sessions
    ADD CONSTRAINT ck_scan_sessions_ts_source
        CHECK (frame_timestamp_source IS NULL OR frame_timestamp_source IN ('HARDWARE','WALL_CLOCK','MIXED')),
    ADD CONSTRAINT ck_scan_sessions_ae_lock
        CHECK (ae_lock IS NULL OR ae_lock IN ('CONFIRMED','REQUESTED','IGNORED','UNSUPPORTED')),
    ADD CONSTRAINT ck_scan_sessions_awb_lock
        CHECK (awb_lock IS NULL OR awb_lock IN ('CONFIRMED','REQUESTED','IGNORED','UNSUPPORTED'));

ALTER TABLE core.scan_results
    ADD COLUMN mobile_quality_score DOUBLE PRECISION,
    ADD COLUMN spectral_quality_score DOUBLE PRECISION,
    ADD COLUMN spectral_snr_db DOUBLE PRECISION,
    ADD COLUMN quality_score_basis VARCHAR(40),
    ADD COLUMN effective_fps DOUBLE PRECISION,
    ADD COLUMN hr_status VARCHAR(16),
    ADD COLUMN hr_abstention_reason VARCHAR(32),
    ADD COLUMN hrv_withheld_low_fps BOOLEAN,
    ADD COLUMN anemia_applicability VARCHAR(16),
    ADD COLUMN anemia_not_applicable_reason VARCHAR(32),
    ADD COLUMN voice_status VARCHAR(16),
    ADD COLUMN voice_client_values_cleared BOOLEAN,
    ADD COLUMN voice_clip_fraction DOUBLE PRECISION,
    ADD COLUMN voice_shimmer_withheld BOOLEAN,
    ADD COLUMN contract_revision SMALLINT;

-- Old rows were scored as max(mobile, spectral) before PR #1. Label them so trends never mix bases.
-- hr_status stays NULL on legacy rows: unknown, never "measured".
UPDATE core.scan_results SET quality_score_basis = 'LEGACY_MAX_OF_MOBILE_AND_SPECTRAL'
WHERE quality_score_basis IS NULL;

ALTER TABLE core.scan_results
    ADD CONSTRAINT ck_scan_results_hr_status
        CHECK (hr_status IS NULL OR hr_status IN ('MEASURED','ABSTAINED','NOT_ATTEMPTED')),
    ADD CONSTRAINT ck_scan_results_hr_abstained_has_no_hr
        CHECK (hr_status IS DISTINCT FROM 'ABSTAINED' OR (hr_bpm IS NULL AND hrv_ms IS NULL)),
    ADD CONSTRAINT ck_scan_results_anemia_na_has_no_label
        CHECK (anemia_applicability IS DISTINCT FROM 'NOT_APPLICABLE'
               OR (anemia_wellness_label IS NULL AND hb_proxy_score IS NULL));

CREATE TABLE core.scan_result_voice_abstention_reasons (
    scan_result_id UUID NOT NULL,
    reason_order INTEGER NOT NULL,
    reason VARCHAR(40) NOT NULL,
    CONSTRAINT pk_scan_result_voice_reasons PRIMARY KEY (scan_result_id, reason_order),
    CONSTRAINT fk_scan_result_voice_reasons_result
        FOREIGN KEY (scan_result_id) REFERENCES core.scan_results (id) ON DELETE CASCADE
);
