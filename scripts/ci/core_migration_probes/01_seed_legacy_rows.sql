-- Rows in the exact shapes today's JPA entities write (pre-V8).
INSERT INTO core.users (id, created_at, updated_at, oidc_subject, email, display_name, is_active)
VALUES ('00000000-0000-0000-0000-000000000001', now() - INTERVAL '10 days', now() - INTERVAL '10 days',
        'oidc-legacy-1', 'legacy-1@example.com', 'Legacy User', TRUE);

INSERT INTO core.scan_sessions (id, created_at, updated_at, user_id, status, device_model, app_version, completed_at, scan_type)
VALUES ('00000000-0000-0000-0000-0000000000a1', now() - INTERVAL '9 days', now() - INTERVAL '9 days',
        '00000000-0000-0000-0000-000000000001', 'COMPLETED', 'Redmi 12', '1.4.0', now() - INTERVAL '9 days', 'STANDARD');

INSERT INTO core.scan_results (id, created_at, updated_at, session_id, user_id, hr_bpm, hrv_ms, quality_score,
                               anemia_wellness_label, hb_proxy_score, stiffness_index)
VALUES ('00000000-0000-0000-0000-0000000000b1', now() - INTERVAL '9 days', now() - INTERVAL '9 days',
        '00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-000000000001', 71.0, 42.0, 0.83,
        'within_typical_range', 0.61, NULL);

INSERT INTO core.scan_result_flags (scan_result_id, flag_order, flag)
VALUES ('00000000-0000-0000-0000-0000000000b1', 0, 'abstain_reason:low_spectral_snr');

INSERT INTO core.consent_records (id, created_at, updated_at, user_id, action, consent_version, purpose)
VALUES ('00000000-0000-0000-0000-0000000000c1', now() - INTERVAL '10 days', now() - INTERVAL '10 days',
        '00000000-0000-0000-0000-000000000001', 'GRANTED', '1.0', 'wellness_screening');

INSERT INTO core.deletion_requests (id, created_at, updated_at, user_id, status)
VALUES ('00000000-0000-0000-0000-0000000000d1', TIMESTAMPTZ '2026-11-01 00:00:00+00', TIMESTAMPTZ '2026-11-01 00:00:00+00',
        '00000000-0000-0000-0000-000000000001', 'PENDING');
INSERT INTO core.deletion_requests (id, created_at, updated_at, user_id, status, purged_at)
VALUES ('00000000-0000-0000-0000-0000000000d2', TIMESTAMPTZ '2026-10-01 00:00:00+00', TIMESTAMPTZ '2026-10-20 00:00:00+00',
        '00000000-0000-0000-0000-000000000001', 'COMPLETED', TIMESTAMPTZ '2026-10-20 00:00:00+00');
INSERT INTO core.deletion_requests (id, created_at, updated_at, user_id, status, failure_reason)
VALUES ('00000000-0000-0000-0000-0000000000d3', TIMESTAMPTZ '2026-10-05 00:00:00+00', TIMESTAMPTZ '2026-10-06 00:00:00+00',
        '00000000-0000-0000-0000-000000000001', 'FAILED', 'object store timeout');
