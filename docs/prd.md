PRD: Project "PranaScan" (MVP)
Objective: To provide a zero-friction, non-invasive health screening tool that analyzes vital signs and metabolic markers via a 30-second video/voice "Selfie."

> 1. Target Audience
The "Proactive Professional": 25–45 year olds in Tier 1 Indian cities (Bangalore, Mumbai, Delhi) interested in longevity and biohacking.

The "Remote Caregiver": NRIs or urban migrants monitoring the health of aging parents in other cities.

>2. Core User Stories
As a user, I want to check my vitals by looking at my phone so I don't have to carry a pulse oximeter or BP cuff.

As a user, I want my health data to be private and ABDM-compliant so I remain in control of my records.

As an OpenClaw Agent, I want to monitor the user’s "Health Selfie" trends and autonomously suggest a lab test or doctor consult if I detect a 15% deviation from their baseline.

>3. Functional Requirements

A. The "Scanning" Engine
rPPG Module: Must extract Heart Rate (HR), Heart Rate Variability (HRV), and Respiratory Rate from facial capillary blood flow using the front camera.

Skin Tone Calibration: Implement the 2026 Diverse-rPPG standards to ensure accuracy across the Indian Fitzpatrick scale (Types 3–6).

Vocal Biomarker Module: Record a 5-second sustained vowel ("Ahhh") to analyze "Jitter" and "Shimmer" for respiratory stress and vocal cord tension (early metabolic/neurological markers).

B. The Analysis Layer (AI Agentic Skills)
Vascular Age Mapping: Compare rPPG pulse wave morphology against age-standardized datasets to provide a "Vascular Age."

Anemia Screening: Computer Vision analysis of the palpebral conjunctiva (lower eyelid) color to screen for low hemoglobin levels.

C. Integration & Privacy
ABHA Integration: Direct sync with the Ayushman Bharat Health Account via the ABDM Gateway.

DPDP Compliance: "Privacy-by-Design" architecture. Data must be processed on the Edge (local device) where possible; only anonymized metadata moves to the cloud.

>4. Non-Functional Requirements
Latency: Analysis results must be delivered within <15 seconds of scan completion.

Environment Check: The system must proactively detect low lighting or high motion and prompt the user to "Find a steady, bright spot."

Agentic Persistence: The OpenClaw agent must run as a background daemon, providing a "Weekly Vitality Report" via the user’s preferred channel (WhatsApp/Telegram).

>5. Success Metrics (The "Partner" KPIs)
Retention: % of users who perform at least 2 scans per week.

Accuracy: Correlation of ±5% with medical-grade finger-clip oximeters in controlled lighting.

Conversion: % of "At-Risk" alerts that result in a user-initiated lab booking (closing the loop).