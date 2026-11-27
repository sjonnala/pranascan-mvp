-- One probe per line: "<constraint that must reject it>|<statement>". Each must fail with that constraint.
ck_scan_results_hr_abstained_has_no_hr|UPDATE core.scan_results SET hr_bpm = 70.0 WHERE id = '00000000-0000-0000-0000-0000000000b3';
ck_scan_results_hr_abstained_has_no_hr|UPDATE core.scan_results SET hr_status = 'ABSTAINED' WHERE id = '00000000-0000-0000-0000-0000000000b1';
ck_scan_results_anemia_na_has_no_label|UPDATE core.scan_results SET anemia_applicability = 'NOT_APPLICABLE' WHERE id = '00000000-0000-0000-0000-0000000000b1';
ck_scan_results_hr_status|UPDATE core.scan_results SET hr_status = 'MAYBE' WHERE id = '00000000-0000-0000-0000-0000000000b2';
ck_scan_sessions_ts_source|UPDATE core.scan_sessions SET frame_timestamp_source = 'GPS' WHERE id = '00000000-0000-0000-0000-0000000000a2';
ck_scan_sessions_ae_lock|UPDATE core.scan_sessions SET ae_lock = 'LOCKED' WHERE id = '00000000-0000-0000-0000-0000000000a2';
ck_deletion_requests_state|UPDATE core.deletion_requests SET state = 'PURGED' WHERE id = '00000000-0000-0000-0000-0000000000d1';
fk_scan_result_voice_reasons_result|INSERT INTO core.scan_result_voice_abstention_reasons (scan_result_id, reason_order, reason) VALUES ('00000000-0000-0000-0000-0000000000ff', 0, 'HIGH_NOISE');
