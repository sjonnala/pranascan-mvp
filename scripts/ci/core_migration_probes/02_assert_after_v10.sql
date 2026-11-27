-- Fails (ON_ERROR_STOP) on the first assertion that does not hold.
CREATE OR REPLACE FUNCTION pg_temp.must(ok BOOLEAN, what TEXT) RETURNS VOID AS $$
BEGIN
  IF ok IS NOT TRUE THEN RAISE EXCEPTION 'assertion failed: %', what; END IF;
  RAISE NOTICE 'ok: %', what;
END $$ LANGUAGE plpgsql;

-- V8 backfill: legacy result labelled, hr_status stays unknown (never "measured").
SELECT pg_temp.must(quality_score_basis = 'LEGACY_MAX_OF_MOBILE_AND_SPECTRAL' AND hr_status IS NULL
                    AND contract_revision IS NULL, 'V8 legacy scan_result backfill')
FROM core.scan_results WHERE id = '00000000-0000-0000-0000-0000000000b1';

-- V9 backfill
SELECT pg_temp.must(purpose_id = 'legacy.bundled' AND purpose = 'wellness_screening', 'V9 legacy consent backfill')
FROM core.consent_records WHERE id = '00000000-0000-0000-0000-0000000000c1';

-- V10 backfill: PENDING -> RECEIVED, COMPLETED -> COMPLETED, FAILED -> IN_PROGRESS; +30d target, +90d SLA.
SELECT pg_temp.must(state = 'RECEIVED' AND scope = 'ACCOUNT_ALL' AND trigger_source = 'USER_REQUEST'
                    AND target_at = TIMESTAMPTZ '2026-12-01 00:00:00+00'
                    AND sla_due_at = TIMESTAMPTZ '2027-01-30 00:00:00+00'
                    AND completed_at IS NULL AND status = 'PENDING', 'V10 PENDING row backfill')
FROM core.deletion_requests WHERE id = '00000000-0000-0000-0000-0000000000d1';
SELECT pg_temp.must(state = 'COMPLETED' AND completed_at = purged_at, 'V10 COMPLETED row backfill')
FROM core.deletion_requests WHERE id = '00000000-0000-0000-0000-0000000000d2';
SELECT pg_temp.must(state = 'IN_PROGRESS' AND failure_reason = 'object store timeout', 'V10 FAILED row backfill')
FROM core.deletion_requests WHERE id = '00000000-0000-0000-0000-0000000000d3';

-- Current-code (rev-1) INSERT shapes still succeed after V10.
INSERT INTO core.scan_sessions (id, created_at, updated_at, user_id, status, device_model, app_version, scan_type)
VALUES ('00000000-0000-0000-0000-0000000000a2', now(), now(), '00000000-0000-0000-0000-000000000001',
        'INITIATED', 'Galaxy A15', '1.4.0', 'STANDARD');
INSERT INTO core.scan_results (id, created_at, updated_at, session_id, user_id, hr_bpm, quality_score)
VALUES ('00000000-0000-0000-0000-0000000000b2', now(), now(), '00000000-0000-0000-0000-0000000000a2',
        '00000000-0000-0000-0000-000000000001', 66.0, 0.71);
INSERT INTO core.consent_records (id, created_at, updated_at, user_id, action, consent_version, purpose)
VALUES ('00000000-0000-0000-0000-0000000000c2', now(), now(), '00000000-0000-0000-0000-000000000001',
        'REVOKED', '1.0', 'wellness_screening');
INSERT INTO core.deletion_requests (id, created_at, updated_at, user_id, status)
VALUES ('00000000-0000-0000-0000-0000000000d4', now(), now(), '00000000-0000-0000-0000-000000000001', 'PENDING');
SELECT pg_temp.must(quality_score_basis IS NULL, 'rev-1 write after V8 leaves basis NULL (rolling-deploy overlap)')
FROM core.scan_results WHERE id = '00000000-0000-0000-0000-0000000000b2';

-- Rev-2 typed INSERTs succeed.
INSERT INTO core.scan_sessions (id, created_at, updated_at, user_id, status, scan_type, device_platform, capture_path,
                                color_range, ae_lock, awb_lock, delivered_fps, fps_jitter_ms, frame_timestamp_source,
                                contract_revision)
VALUES ('00000000-0000-0000-0000-0000000000a3', now(), now(), '00000000-0000-0000-0000-000000000001', 'COMPLETED',
        'STANDARD', 'ANDROID', 'YUV_PLUGIN', 'LIMITED', 'CONFIRMED', 'REQUESTED', 29.7, 2.1, 'HARDWARE', 2);
INSERT INTO core.scan_results (id, created_at, updated_at, session_id, user_id, quality_score, mobile_quality_score,
                               spectral_quality_score, spectral_snr_db, quality_score_basis, hr_status,
                               hr_abstention_reason, anemia_applicability, anemia_not_applicable_reason,
                               voice_status, voice_client_values_cleared, contract_revision)
VALUES ('00000000-0000-0000-0000-0000000000b3', now(), now(), '00000000-0000-0000-0000-0000000000a3',
        '00000000-0000-0000-0000-000000000001', 0.18, 0.83, 0.18, 1.9, 'SPECTRAL', 'ABSTAINED',
        'LOW_SPECTRAL_SNR', 'NOT_APPLICABLE', 'NO_CONJUNCTIVAL_ROI', 'ABSTAINED', TRUE, 2);
INSERT INTO core.scan_result_voice_abstention_reasons (scan_result_id, reason_order, reason)
VALUES ('00000000-0000-0000-0000-0000000000b3', 0, 'HIGH_NOISE');
INSERT INTO core.consent_records (id, created_at, updated_at, user_id, action, consent_version, purpose, purpose_id,
                                  notice_version, age_attested_18plus, capture_channel, prev_consent_id)
VALUES ('00000000-0000-0000-0000-0000000000c3', now(), now(), '00000000-0000-0000-0000-000000000001', 'GRANTED', '2.0',
        'scan.oneoff', 'scan.oneoff', '2027.1', TRUE, 'APP', '00000000-0000-0000-0000-0000000000c1');
INSERT INTO core.deletion_audit (id, created_at, deletion_request_id, from_state, to_state, actor)
VALUES ('00000000-0000-0000-0000-0000000000e1', now(), '00000000-0000-0000-0000-0000000000d1', 'RECEIVED', 'VERIFIED',
        'system:verifier');

SELECT pg_temp.must((SELECT count(*) FROM core.scan_result_voice_abstention_reasons) = 1, 'voice reason row stored');
