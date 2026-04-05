/**
 * PranaScan shared TypeScript types.
 *
 * IMPORTANT: These types represent wellness indicators only.
 * Do NOT add any diagnostic fields or terminology.
 */

// ─── Auth ────────────────────────────────────────────────────────────────────

export interface CoreUserProfile {
  id: string;
  oidcSubject: string;
  email: string | null;
  displayName: string;
  phoneE164: string | null;
  avatarUrl: string | null;
  active: boolean;
  lastLoginAt: string | null;
  createdAt: string;
  updatedAt: string;
}

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

// ─── Quality ─────────────────────────────────────────────────────────────────

export interface QualityMetrics {
  lighting_score: number;
  motion_score: number;
  face_confidence: number;
  audio_snr_db: number;
}

export type ScanType = 'standard' | 'deep_dive';

export type QualityFlag =
  | 'low_lighting'
  | 'borderline_lighting'
  | 'motion_detected'
  | 'face_not_detected'
  | 'partial_occlusion_suspected'
  | 'poor_thumb_contact'
  | 'borderline_thumb_contact'
  | 'low_signal_quality'
  | 'height_required_for_stiffness_index'
  | 'insufficient_cycles_for_morphology'
  | 'morphology_peaks_not_found'
  | 'high_noise'
  | 'borderline_noise'
  | 'accented_vowel_accommodated'
  | 'partial_scan';

export interface QualityGateResult {
  passed: boolean;
  flags: QualityFlag[];
  metrics: QualityMetrics;
  overallScore: number;
}

// ─── Scan ────────────────────────────────────────────────────────────────────

export interface ScanSession {
  id: string;
  user_id: string;
  status: 'initiated' | 'completed' | 'failed' | 'rejected';
  scan_type: ScanType;
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
  hr_bpm: number | null;
  hrv_ms: number | null;
  spo2: number | null;
  stiffness_index: number | null;
  respiratory_rate: number | null;
  voice_jitter_pct: number | null;
  voice_shimmer_pct: number | null;
  quality_score: number;
  flags: QualityFlag[];
  trend_alert: 'consider_lab_followup' | null;
  created_at: string;
}

export interface ScanSessionWithResult {
  session: ScanSession;
  result: ScanResult | null;
}

// ─── Feedback ────────────────────────────────────────────────────────────────

export type UsefulResponse = 'useful' | 'needs_work';

export interface ScanFeedback {
  id: string;
  session_id: string;
  user_id: string;
  useful_response: UsefulResponse;
  nps_score: number | null;
  comment: string | null;
  created_at: string;
}

export interface ScanFeedbackPayload {
  session_id: string;
  useful_response: UsefulResponse;
  nps_score?: number;
  comment?: string;
}

// ─── Frame data ──────────────────────────────────────────────────────────────

export interface FrameSample {
  t_ms: number;
  r_mean: number;
  g_mean: number;
  b_mean: number;
}

// ─── Scan payload sent to backend ────────────────────────────────────────────

export interface ScanResultPayload {
  scan_type: ScanType;
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
  user_height_cm?: number;
  frame_data?: FrameSample[];
  frame_r_mean?: number;
  frame_g_mean?: number;
  frame_b_mean?: number;
}
