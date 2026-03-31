# Data Contracts

## API Surface

All backend routes are mounted under `/api/v1`.

## Authentication Endpoints

| Method | Path | Auth Required | Purpose |
| --- | --- | --- | --- |
| POST | `/auth/token` | No | Issue access and refresh tokens for a `user_id` |
| POST | `/auth/refresh` | No | Exchange refresh token for a new pair |
| GET | `/auth/me` | Yes | Return authenticated subject |

## Consent Endpoints

| Method | Path | Auth Required | Purpose |
| --- | --- | --- | --- |
| POST | `/consent` | Yes | Append a granted-consent record |
| POST | `/consent/revoke` | Yes | Append a revoke record |
| POST | `/consent/deletion-request` | Yes | Append a deletion-request record |
| GET | `/consent/status` | No | Compute current consent state for a `user_id` |

## Scan Endpoints

| Method | Path | Auth Required | Purpose |
| --- | --- | --- | --- |
| POST | `/scans/sessions` | Yes | Create a new scan session |
| PUT | `/scans/sessions/{id}/complete` | Yes | Submit scan metrics and complete the session |
| GET | `/scans/sessions/{id}` | Yes | Fetch a session and its result |
| GET | `/scans/history` | Yes | Fetch paginated history with trend deltas |

## Audit Endpoints

| Method | Path | Auth Required | Purpose |
| --- | --- | --- | --- |
| GET | `/audit/logs` | Yes | Paginated immutable audit-log listing |

## Core Request Models

### `ScanSessionCreateRequest`

Fields:

- `user_id`
- `device_model`
- `app_version`

Behavior:

- scan creation ignores the body `user_id` and uses the authenticated subject

### `ScanResultSubmit`

Primary fields:

- optional metrics:
  - `hr_bpm`
  - `hrv_ms`
  - `respiratory_rate`
  - `voice_jitter_pct`
  - `voice_shimmer_pct`
- quality:
  - `quality_score`
  - `lighting_score`
  - `motion_score`
  - `face_confidence`
  - `audio_snr_db`
- flags:
  - `flags`
- optional fallback feature inputs:
  - `frame_data`
  - `audio_samples`
- optional on-device anemia inputs:
  - `frame_r_mean`
  - `frame_g_mean`
  - `frame_b_mean`

### `ScanResultResponse`

Current backend response includes:

- all main wellness metrics
- `quality_score`
- `flags`
- `trend_alert`
- `vascular_age_estimate`
- `vascular_age_confidence`
- `hb_proxy_score`
- `anemia_wellness_label`
- `anemia_confidence`
- `created_at`

## Mobile-To-Backend Contract

### Current Main Mobile Path

The current mobile app typically submits:

- final scalar vitals from on-device rPPG
- final scalar voice metrics from on-device voice DSP
- quality metadata
- aggregate RGB means for anemia heuristics

It typically omits:

- `frame_data`
- `audio_samples`

### Backward-Compatible Backend Path

The backend still supports:

- `frame_data` for server-side rPPG
- `audio_samples` for server-side voice DSP

This is why both edge-first and fallback processing code paths currently exist.

## Consent Data Model

Table: `consent_records`

Semantics:

- append-only
- no in-place update path
- deletion is modeled as a request event plus eventual scheduled handling

Important columns:

- `id`
- `user_id`
- `action`
- `consent_version`
- `purpose`
- `created_at`
- `deletion_scheduled_at`
- `deleted_at`

Allowed consent actions:

- `granted`
- `revoked`
- `deletion_requested`

## Scan Data Model

### `scan_sessions`

Purpose:

- one row per scan attempt

Important columns:

- `id`
- `user_id`
- `status`
- `device_model`
- `app_version`
- `created_at`
- `completed_at`

Allowed statuses:

- `initiated`
- `completed`
- `failed`
- `rejected`

### `scan_results`

Purpose:

- one row per completed scan session

Important columns:

- identifiers:
  - `id`
  - `session_id`
  - `user_id`
- metrics:
  - `hr_bpm`
  - `hrv_ms`
  - `respiratory_rate`
  - `voice_jitter_pct`
  - `voice_shimmer_pct`
- quality:
  - `quality_score`
  - `lighting_score`
  - `motion_score`
  - `face_confidence`
  - `audio_snr_db`
- workflow:
  - `flags`
  - `trend_alert`
- secondary heuristics:
  - `vascular_age_estimate`
  - `vascular_age_confidence`
  - `hb_proxy_score`
  - `anemia_wellness_label`
  - `anemia_confidence`
- timestamp:
  - `created_at`

## Audit Data Model

Table: `audit_logs`

Purpose:

- immutable operational record of API activity

Important columns:

- `id`
- `user_id`
- `action`
- `http_method`
- `http_path`
- `http_status`
- `duration_ms`
- `ip_address`
- `user_agent`
- `detail`
- `created_at`

## Privacy And Storage Matrix

| Data Type | Mobile Storage | Network | Backend Storage |
| --- | --- | --- | --- |
| Pseudonymous user ID | AsyncStorage | Yes | Yes |
| Consent state cache | AsyncStorage | Yes | Yes |
| Raw video | In-memory during scan | No in current main path | No |
| Raw audio | In-memory during scan | No in current main path | No |
| Frame RGB means | In-memory during scan | Optional fallback path only | Not persisted directly |
| Audio amplitude samples | In-memory during scan | Optional fallback path only | Not persisted directly |
| Final wellness metrics | In-memory then submitted | Yes | Yes |
| Audit request metadata | No | Internal only | Yes |

## Contract Mismatches New Engineers Should Notice

### Backend Richer Than Mobile Types

Backend returns vascular-age and anemia-screening fields.
Current mobile `ScanResult` TypeScript type does not model them.

### Hybrid Signal-Processing Contract

The backend schemas still expose `frame_data` and `audio_samples`, but the
current mobile flow largely submits already-processed scalar indicators.

### Consent Auth Contract

Consent write routes require auth, but the current router implementation
does not strictly enforce that the request-body `user_id` matches the token
subject. Treat that as a known security-hardening gap.
