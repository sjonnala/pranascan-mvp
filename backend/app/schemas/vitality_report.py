"""Pydantic schemas for vitality report endpoints."""

from datetime import datetime

from pydantic import BaseModel


class MetricSummarySchema(BaseModel):
    name: str
    unit: str
    current_avg: float | None
    prior_avg: float | None
    delta: float | None
    scan_count: int


class VitalityReportResponse(BaseModel):
    id: str
    user_id: str
    period_start: datetime
    period_end: datetime
    scan_count: int
    alert_count: int
    avg_hr_bpm: float | None
    avg_hrv_ms: float | None
    avg_respiratory_rate: float | None
    avg_voice_jitter_pct: float | None
    avg_voice_shimmer_pct: float | None
    delta_hr_bpm: float | None
    delta_hrv_ms: float | None
    latest_vascular_age_estimate: float | None
    latest_vascular_age_confidence: float | None
    latest_anemia_label: str | None
    latest_anemia_confidence: float | None
    summary_text: str
    generated_at: datetime

    model_config = {"from_attributes": True}
