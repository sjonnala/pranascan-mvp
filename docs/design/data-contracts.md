# Data Contracts

## API Surface

Public product routes are mounted under `service-core` at `/api/v1`.
Internal compute routes are exposed from `service-intelligence` over gRPC.
The planned Circle/Vitality Glow feed routes are defined in
[vitality-glow-feed-contract.md](./vitality-glow-feed-contract.md).

## Core Authentication Endpoint

| Method | Path | Auth Required | Purpose |
| --- | --- | --- | --- |
| GET | `/auth/me` | Yes | Return authenticated subject |

## Consent Endpoints

| Method | Path | Auth Required | Purpose |
| --- | --- | --- | --- |
| POST | `/consent` | Yes | Append a granted-consent record |
| POST | `/consent/revoke` | Yes | Append a revoke record |
| POST | `/consent/deletion-request` | Yes | Append a deletion-request record |
| GET | `/consent/status` | Yes | Compute current consent state for the authenticated subject |

## Scan Endpoints

| Method | Path | Auth Required | Purpose |
| --- | --- | --- | --- |
| POST | `/scans/sessions` | Yes | Create a new scan session |
| PUT | `/scans/sessions/{id}/complete` | Yes | Submit scan metrics and complete the session |
| GET | `/scans/sessions/{id}` | Yes | Fetch a session and its result |
| GET | `/scans/sessions/history` | Yes | Fetch paginated history with trend deltas |

## Social Endpoints

| Method | Path | Auth Required | Purpose |
| --- | --- | --- | --- |
| GET | `/social/connections` | Yes | List the viewer's social connections |
| POST | `/social/connections` | Yes | Create a new connection request |
| POST | `/social/connections/{connectionId}/accept` | Yes | Accept a pending connection |
| POST | `/social/connections/{connectionId}/decline` | Yes | Decline a pending connection |
| GET | `/business/vitality-streak` | Yes | Return the viewer's streak summary |

Feed-specific APIs such as `/social/circle/summary`, `/social/feed`, reactions,
comments, discovery, and social preferences are intentionally documented in the
dedicated Vitality Glow contract doc until they are implemented in
`service-core`.

## Audit Endpoints

| Method | Path | Auth Required | Purpose |
| --- | --- | --- | --- |
| GET | `/audit/logs` | Yes | Paginated immutable audit-log listing |

## Internal Intelligence gRPC Contract

Service: `pranapulse.intelligence.scan.v1.ScanIntelligenceService`

Method:

- `EvaluateScan`

Request fields:

- scalar metrics such as `hr_bpm`, `hrv_ms`, `respiratory_rate`
- quality inputs such as `quality_score`, `lighting_score`, `motion_score`,
  `face_confidence`, `audio_snr_db`
- optional fallback inputs:
  - `frame_data`
  - `audio_samples`
  - `image_bytes`
  - `video_bytes`
- aggregate RGB means:
  - `frame_r_mean`
  - `frame_g_mean`
  - `frame_b_mean`

Response fields:

- quality-gate decision and flags
- main vitals and voice metrics
- `spo2`
- vascular-age outputs
- anemia heuristic outputs
- optional rejection reason

## Core Request Models

### `ScanSessionCreateRequest`

Fields:

- `device_model`
- `app_version`

Behavior:

- scan creation derives the user from the authenticated subject

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

Current core response includes:

- all main wellness metrics
- `quality_score`
- `flags`
- `trend_alert`
- `spo2`
- `vascular_age_estimate`
- `vascular_age_confidence`
- `hb_proxy_score`
- `anemia_wellness_label`
- `anemia_confidence`
- `created_at`

## Mobile-To-Backend Contract

### Current Main Mobile Path

The current mobile app typically submits:

- final scalar vitals from on-device processing
- final scalar voice metrics from on-device DSP
- quality metadata
- aggregate RGB means for anemia heuristics

It typically omits:

- `frame_data`
- `audio_samples`

### Fallback Compute Path

The internal intelligence contract still supports:

- `frame_data` for server-side rPPG
- `audio_samples` for server-side voice DSP
- `image_bytes` and `video_bytes` for raw media ingestion

This is why both capture-first and server-side fallback compute paths currently exist.

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
| OIDC access token | SecureStore | Yes | No |
| Consent state cache | AsyncStorage | Yes | Yes |
| Raw video | In-memory during scan | No in current main path | No |
| Raw audio | In-memory during scan | No in current main path | No |
| Frame RGB means | In-memory during scan | Optional fallback path only | Not persisted directly |
| Audio amplitude samples | In-memory during scan | Optional fallback path only | Not persisted directly |
| Final wellness metrics | In-memory then submitted | Yes | Yes |
| Audit request metadata | No | Internal only | Yes |

## Contract Mismatches New Engineers Should Notice

### Core Richer Than Some Mobile Views

`service-core` returns vascular-age, anemia-screening, and `spo2` fields.
Make sure mobile result types stay synchronized with the rendered UI.

### Hybrid Signal-Processing Contract

The intelligence contract still exposes `frame_data`, `audio_samples`, and raw
media bytes, but the current mobile flow largely submits already-processed
scalar indicators.
