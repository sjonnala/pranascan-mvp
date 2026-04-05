# PranaScan — Architecture

## Overview

PranaScan follows an **edge-first, privacy-by-design** architecture. Heavy signal processing
runs on the mobile device; the backend stores only anonymised metric snapshots.

```
┌─────────────────────────────────────────────────────────────┐
│                    User's Mobile Device                      │
│                                                              │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │ Camera   │──▶│ rPPG Engine  │──▶│                      │ │
│  │ (30s)    │   │ (on-device)  │   │  ScanOrchestrator    │ │
│  └──────────┘   └──────────────┘   │  - Quality gate      │ │
│                                    │  - Metric assembly   │ │
│  ┌──────────┐   ┌──────────────┐   │  - Trend delta       │ │
│  │ Mic      │──▶│ Voice Engine │──▶│                      │ │
│  │ (5s)     │   │ (on-device)  │   └──────────┬───────────┘ │
│  └──────────┘   └──────────────┘              │             │
└───────────────────────────────────────────────┼─────────────┘
                                                │ HTTPS (metrics only)
                                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
│                                                              │
│  ┌──────────────┐  ┌────────────┐  ┌────────────────────┐  │
│  │ /consent     │  │ /scans     │  │ /audit             │  │
│  │ router       │  │ router     │  │ router             │  │
│  └──────┬───────┘  └─────┬──────┘  └─────────┬──────────┘  │
│         │                │                   │              │
│  ┌──────▼───────────────▼───────────────────▼──────────┐  │
│  │              Service Layer                            │  │
│  │  ConsentService │ QualityGateService │ AuditService   │  │
│  └──────────────────────────┬──────────────────────────┘  │
│                             │                              │
│  ┌──────────────────────────▼──────────────────────────┐  │
│  │         PostgreSQL (SQLAlchemy 2.0 async)            │  │
│  │  consents | scan_sessions | scan_results | audit_log │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **Consent check** — App verifies active consent before any scan
2. **Quality gate** — On-device checks for lighting, motion, face confidence, audio SNR
3. **Scan session created** — Backend issues session ID
4. **On-device processing** — rPPG + voice analysis runs locally
5. **Result submission** — Only metric values (no raw video/audio) sent to backend
6. **Audit logging** — Every API call auto-logged (middleware), immutable
7. **Trend computation** — Backend compares to prior 7-day baseline, flags anomalies

## Privacy Guarantees

| Data | Handling |
|------|---------|
| Raw video frames | Never leaves device |
| Raw audio samples | Never leaves device |
| Metric values (HR, HRV, etc.) | Encrypted in transit (TLS), stored with user_id |
| user_id | Pseudonymous UUID — no PII required |
| Consent record | Append-only; deletion requests honoured after 30-day legal hold |
| Audit log | Immutable; no delete endpoints |

## Quality Thresholds

| Metric | Minimum | Reject reason |
|--------|---------|--------------|
| `lighting_score` | > 0.4 | Poor lighting |
| `motion_score` | > 0.95 | Excessive movement |
| `face_confidence` | > 0.8 | Face not detected |
| `audio_snr_db` | > 15.0 dB | Background noise too high |

## Scan Result Schema

```json
{
  "hr_bpm": 72.4,
  "hrv_ms": 45.2,
  "respiratory_rate": 16.1,
  "voice_jitter_pct": 0.42,
  "voice_shimmer_pct": 1.8,
  "quality_score": 0.91,
  "flags": [],
  "trend_alert": null
}
```

`trend_alert` values (when present): `"consider_lab_followup"` — never diagnostic language.

## Post-Scan Latency Budget

| Step | Budget |
|------|--------|
| On-device processing | ≤ 10s |
| Network round-trip | ≤ 2s |
| Backend processing | ≤ 1s |
| UI render | ≤ 2s |
| **Total** | **≤ 15s** |
