/**
 * PranaScan shared TypeScript types.
 *
 * IMPORTANT: These types represent wellness indicators only.
 * Do NOT add any diagnostic fields or terminology.
 */

// ─── Consent ─────────────────────────────────────────────────────────────────

export interface ConsentRecord {
  id: string;
  user_id: string;
  action: 'granted' | 'revoked' | 'deletion_requested';
  consent_version: string;
  purpose: string;
  created_at: string;
  deletion_scheduled_at?: string | null;
}

export interface ConsentStatus {
  user_id: string;
  has_active_consent: boolean;
  consent_version: string | null;
  granted_at: string | null;
  revoked_at: string | null;
  deletion_requested: boolean;
  deletion_scheduled_at: string | null;
}

// ─── Quality ──────────────────────────────────────────────────────────────────

export interface QualityMetrics {
  lighting_score: number; // 0–1 (min 0.4)
  motion_score: number; // 0–1 (min 0.95)
  face_confidence: number; // 0–1 (min 0.8)
  audio_snr_db: number; // dB (min 15.0)
}

export type QualityFlag =
  | 'low_lighting'
  | 'motion_detected'
  | 'face_not_detected'
  | 'high_noise'
  | 'partial_scan';

export interface QualityGateResult {
  passed: boolean;
  flags: QualityFlag[];
  metrics: QualityMetrics;
  overallScore: number;
}

// ─── Scan ─────────────────────────────────────────────────────────────────────

export interface ScanSession {
  id: string;
  user_id: string;
  status: 'initiated' | 'completed' | 'failed' | 'rejected';
  device_model: string | null;
  app_version: string | null;
  created_at: string;
  completed_at: string | null;
}

/**
 * Wellness indicator result — NOT a diagnostic report.
 * All values are estimates for informational wellness tracking only.
 */
export interface ScanResult {
  id: string;
  session_id: string;
  user_id: string;

  /** Estimated heart rate (wellness indicator) */
  hr_bpm: number | null;
  /** Estimated heart rate variability (wellness indicator) */
  hrv_ms: number | null;
  /** Estimated respiratory rate (wellness indicator) */
  respiratory_rate: number | null;
  /** Voice jitter percentage (wellness indicator) */
  voice_jitter_pct: number | null;
  /** Voice shimmer percentage (wellness indicator) */
  voice_shimmer_pct: number | null;

  quality_score: number;
  flags: QualityFlag[];

  /**
   * Trend alert — only "consider_lab_followup" or null.
   * Never diagnostic language.
   */
  trend_alert: 'consider_lab_followup' | null;

  created_at: string;
}

export interface ScanSessionWithResult {
  session: ScanSession;
  result: ScanResult | null;
}

// ─── Frame data ───────────────────────────────────────────────────────────────

/**
 * Per-frame colour channel means sent to the backend for server-side rPPG.
 * Raw pixels NEVER leave the device — only per-frame aggregate means.
 */
export interface FrameSample {
  t_ms: number;    // milliseconds from scan start
  r_mean: number;  // 0–255 mean red channel
  g_mean: number;  // 0–255 mean green channel
  b_mean: number;  // 0–255 mean blue channel
}

// ─── Scan payload sent to backend ────────────────────────────────────────────

export interface ScanResultPayload {
  hr_bpm?: number;
  hrv_ms?: number;
  respiratory_rate?: number;
  voice_jitter_pct?: number;
  voice_shimmer_pct?: number;
  quality_score: number;
  lighting_score?: number;
  motion_score?: number;
  face_confidence?: number;
  audio_snr_db?: number;
  flags: QualityFlag[];
  /** Per-frame RGB means for server-side rPPG processing. Raw video stays on device. */
  frame_data?: FrameSample[];
  /** Normalised audio amplitude samples for server-side voice DSP. */
  audio_samples?: number[];
}

// ─── Navigation ──────────────────────────────────────────────────────────────

export type RootStackParamList = {
  Consent: undefined;
  Scan: { userId: string };
  Results: { sessionId: string; userId: string };
};
