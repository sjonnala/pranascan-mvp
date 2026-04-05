Got both. Building the plan now.

---

# 🧘 PranaScan — 30-Day MVP Execution Plan

**Goal:** Ship a functional, privacy-compliant, clinically-grounded health selfie screening MVP in 30 days — rPPG vitals + vocal biomarker analysis + agentic trend monitoring.

**Assumptions:**
- Small cross-functional team: 1 ML engineer, 1 mobile dev, 1 service-intelligence/infra, 1 product/design, 1 compliance lead (part-time)
- React Native or Flutter for mobile; Python/FastAPI for backend metadata layer
- ABDM sandbox credentials available by Day 3
- Diverse-rPPG 2026 reference dataset licensed or accessible

---

## 📅 Week 1 (Days 1–7): Foundation & Scanning Core

**Theme: Get the camera and mic capturing clean, usable signals**

### Milestones
- [ ] **D1** — Repo scaffolded, CI/CD pipeline live, team onboarded to branching strategy
- [ ] **D2** — Environment check module live: detects low light, high motion, prompts user correction
- [ ] **D3** — rPPG pipeline: 30s video capture → raw signal extraction (HR baseline) working on-device
- [ ] **D5** — Skin tone calibration module integrated (Fitzpatrick Types 3–6 via Diverse-rPPG 2026 spec)
- [ ] **D7** — Vocal biomarker module: 5s "Ahhh" capture → Jitter + Shimmer extraction working locally

### Owners
| Task | Owner |
|---|---|
| rPPG pipeline | ML Engineer |
| Environment check UX | Mobile Dev + Designer |
| Vocal module | ML Engineer |
| Skin tone dataset integration | ML Engineer |
| CI/CD + repo | Backend/Infra |

### Dependencies
- Diverse-rPPG 2026 reference dataset access ← **block if missing**
- Device test matrix (Android mid-range + iPhone) agreed on Day 1

### Risks
- 🔴 Skin tone calibration accuracy on Indian Fitzpatrick scale may require > 1 week of tuning — mitigation: stub with flag + "accuracy may vary" disclaimer for MVP
- 🟡 Mic quality variance across Android devices (jitter/shimmer noise floor) — mitigation: minimum SNR threshold gate before analysis

### KPI Targets (Week 1)
| Metric | Target |
|---|---|
| HR extraction accuracy (controlled lab, Type 3–4 skin) | ±10% vs finger-clip oximeter |
| Jitter/Shimmer extraction | Signal captured on ≥90% of test recordings |
| Environment check trigger rate | Fires correctly on 100% of low-light test cases |

---

## 📅 Week 2 (Days 8–14): Analysis Layer + Privacy Architecture

**Theme: Make the signals meaningful; lock down the data flow**

### Milestones
- [ ] **D8** — On-device processing architecture finalized: define what stays local vs. what metadata moves to cloud
- [ ] **D9** — HRV extraction from rPPG waveform live (SDNN / RMSSD)
- [ ] **D10** — Respiratory Rate proxy derived from rPPG signal
- [ ] **D11** — Vascular Age mapping: pulse wave morphology → age-standardized score (v1, heuristic model)
- [ ] **D12** — Anemia screening module: palpebral conjunctiva color CV model integrated
- [ ] **D13** — DPDP consent flow designed and implemented: explicit opt-in, audit log, data deletion path
- [ ] **D14** — End-to-end scan → result flow working in internal build; <15s latency validated

### Owners
| Task | Owner |
|---|---|
| HRV + RR extraction | ML Engineer |
| Vascular Age v1 model | ML Engineer |
| Anemia CV module | ML Engineer |
| On-device vs cloud data flow architecture | Backend/Infra |
| DPDP consent + audit log | Backend/Infra + Compliance Lead |
| UX for results screen | Designer + Mobile Dev |

### Dependencies
- Week 1 rPPG pipeline stable (no regressions)
- Compliance lead sign-off on data minimization schema
- Age-standardized pulse wave dataset for Vascular Age benchmarking

### Risks
- 🔴 Anemia screening accuracy — conjunctiva color CV is sensitive to lighting; may need to gate behind "good lighting confirmed" flow — mitigation: add confidence score, show result only if confidence > threshold
- 🟡 <15s latency target may be strained by on-device CV inference on low-end Android — mitigation: benchmark on Redmi Note 11 class device by D14
- 🟡 DPDP compliance scope may expand — mitigation: use DPDP-lite checklist scoped to MVP, defer full DPA registration to post-MVP

### KPI Targets (Week 2)
| Metric | Target |
|---|---|
| HRV (RMSSD) accuracy | ±15% vs Polar H10 chest strap in bench test |
| End-to-end scan latency | <15s on mid-range Android (Snapdragon 680+) |
| Consent flow completion rate (internal testing) | 100% — no dark patterns, clear opt-out |
| Anemia module confidence threshold pass rate | ≥70% of scans in good lighting |

---

## 📅 Week 3 (Days 15–21): ABDM Integration + Agentic Trend Layer

**Theme: Connect to the health ecosystem; make the agent proactively useful**

### Milestones
- [ ] **D15** — ABHA (Ayushman Bharat Health Account) sandbox integration live: scan results sync to ABDM Gateway
- [ ] **D17** — Baseline establishment logic: user's first 3 scans create rolling baseline per metric
- [ ] **D18** — Trend deviation engine: computes `abs(current - baseline) / baseline * 100`, flags ≥15% deviation
- [ ] **D19** — Agentic alert system: OpenClaw background daemon triggers "lab/doctor follow-up" recommendation (never diagnosis language) via WhatsApp or Telegram
- [ ] **D20** — Weekly Vitality Report template live: auto-generated, delivered via preferred channel
- [ ] **D21** — Internal pilot: 5–10 team members run daily scans for 7 days; collect feedback

### Owners
| Task | Owner |
|---|---|
| ABDM Gateway integration | Backend/Infra |
| Baseline + deviation engine | ML Engineer + Backend/Infra |
| Agentic daemon (OpenClaw skill wiring) | Backend/Infra + Product |
| Alert messaging copy | Product + Compliance Lead |
| Weekly report template | Designer + Product |
| Internal pilot coordination | Product |

### Dependencies
- ABDM sandbox credentials + HIU/HIP registration approved ← **critical path**
- Alert language reviewed by Compliance (no diagnostic claims)
- WhatsApp Business API or Telegram Bot token provisioned

### Risks
- 🔴 ABDM sandbox approval timeline unpredictable (can take 1–2 weeks) — mitigation: begin application by D1, build integration layer against mock API in parallel
- 🟡 Agentic alert fatigue: too many 15% deviation flags may erode trust — mitigation: minimum 3-scan baseline required before any alerts fire; cap at 1 alert per 48h per metric
- 🟡 WhatsApp Business API approval latency — mitigation: Telegram as fallback from Day 1

### KPI Targets (Week 3)
| Metric | Target |
|---|---|
| ABDM sync success rate (sandbox) | ≥95% of completed scans |
| Deviation engine accuracy | Zero false-negative alerts in test scenario set |
| Internal pilot scan completion | ≥8/10 team members complete ≥5 scans each |
| Alert language compliance | 0 diagnostic claim flags in compliance review |

---

## 📅 Week 4 (Days 22–30): Validation, Hardening & Pilot Launch

**Theme: Prove it works on real people; ship to a closed beta**

### Milestones
- [ ] **D22** — Accuracy bench test: 20-person controlled session, compare HR/HRV/SpO2 proxy vs medical-grade finger-clip oximeter
- [ ] **D24** — Skin tone accuracy audit: ensure Fitzpatrick 5–6 results within acceptable error bounds
- [ ] **D25** — Security audit: data at rest + in transit, consent log integrity, no PII in cloud metadata
- [ ] **D26** — Bug bash: performance, edge cases (glasses, beards, low-light recovery, accented vowels)
- [ ] **D27** — Closed beta onboarding: 50 users (Proactive Professionals + Remote Caregivers mix)
- [ ] **D28** — Feedback loop live: in-app "Was this scan useful?" + NPS prompt
- [ ] **D30** — Week 4 review: KPI readout, go/no-go for broader rollout, post-MVP backlog locked

### Owners
| Task | Owner |
|---|---|
| Bench accuracy test | ML Engineer + Product |
| Skin tone audit | ML Engineer |
| Security audit | Backend/Infra + Compliance Lead |
| Bug bash | Full team |
| Beta user recruitment | Product |
| Feedback instrumentation | Mobile Dev + Backend/Infra |

### Dependencies
- Weeks 1–3 features stable with no P0 bugs
- 20 volunteer participants for bench test (IRB waiver or informed consent in place)
- Beta user list pre-recruited by D20

### Risks
- 🔴 Accuracy bench test fails ±5% target — mitigation: if delta is ±8–10%, ship with "screening tool, not diagnostic device" framing; flag as P0 for post-MVP model improvement
- 🟡 Beta users drop off after first scan — mitigation: WhatsApp nudge at 72h if no second scan; "streak" mechanic in UI
- 🟡 ABDM production approval still pending by D30 — mitigation: ship beta with ABHA link as optional, not required

### KPI Targets (Week 4 / MVP Exit Criteria)
| KPI | Target | Notes |
|---|---|---|
| HR accuracy | ±5% vs finger-clip oximeter | Primary accuracy KPI |
| HRV accuracy | ±15% vs Polar H10 | Secondary |
| Scan completion rate | ≥85% of initiated scans complete | UX quality signal |
| 2-scans/week retention (beta) | ≥40% of beta users | PRD retention KPI |
| At-risk alert → lab booking conversion | ≥10% | PRD conversion KPI (early signal) |
| Post-scan latency | <15s on Snapdragon 680+ | NFR |

---

## 🗂️ MVP Scope vs Post-MVP

| Feature | MVP | Post-MVP |
|---|---|---|
| HR, HRV, Respiratory Rate (rPPG) | ✅ | — |
| Jitter + Shimmer (vocal) | ✅ | — |
| Vascular Age (heuristic v1) | ✅ | → Clinical-grade model v2 |
| Anemia screening (CV) | ✅ (confidence-gated) | → Higher accuracy model |
| Skin tone calibration (Types 3–6) | ✅ | → Types 1–2 edge cases |
| ABDM/ABHA sync | ✅ (sandbox → prod) | → Full HIU/HIP certification |
| Agentic weekly report | ✅ | → Personalized AI coaching |
| Blood glucose / lactate (Rockley-style) | ❌ | → Post-FDA/CDSCO cleared hardware |
| Wearable PPG integration | ❌ | → Oura / Galaxy Watch ingestion |
| Teleconsult booking integration | ❌ | → Practo / Apollo partner API |

---

## ✅ Compliance Checklist

- [ ] DPDP consent modal (explicit, granular, revocable)
- [ ] Audit log for every data access event
- [ ] Data deletion endpoint tested
- [ ] No PII in cloud metadata layer (only anonymized scan IDs)
- [ ] ABDM HIU/HIP registration application submitted (Day 1)
- [ ] Alert copy reviewed: zero diagnostic language
- [ ] "Screening tool, not diagnostic device" disclaimer on every results screen

---

## 🔁 Next 3 Actions (Start Monday)

1. **Provision infra + dataset access** — ABDM sandbox credentials, Diverse-rPPG 2026 dataset, WhatsApp Business API application — all on Day 1, no exceptions
2. **Benchmark device matrix** — Lock test devices by D1 (minimum: Redmi Note 11, Samsung A53, iPhone 13); latency and accuracy targets depend on this
3. **Recruit beta cohort early** — Target 50 beta users (25 Proactive Professionals, 25 Remote Caregivers) by Week 3; don't wait until Week 4 to start outreach