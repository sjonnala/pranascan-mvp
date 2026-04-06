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

export interface ScanHistoryItem {
  session: ScanSession;
  result: ScanResult | null;
  hr_trend_delta: number | null;
  hrv_trend_delta: number | null;
}

export interface ScanHistoryPage {
  items: ScanHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface VitalityReport {
  id: string;
  user_id: string;
  period_start: string;
  period_end: string;
  scan_count: number;
  alert_count: number;
  avg_hr_bpm: number | null;
  avg_hrv_ms: number | null;
  avg_respiratory_rate: number | null;
  avg_voice_jitter_pct: number | null;
  avg_voice_shimmer_pct: number | null;
  delta_hr_bpm: number | null;
  delta_hrv_ms: number | null;
  latest_vascular_age_estimate: number | null;
  latest_vascular_age_confidence: number | null;
  latest_anemia_label: string | null;
  latest_anemia_confidence: number | null;
  summary_text: string;
  generated_at: string;
}

export type VitalityStreakStatus = 'ACTIVE' | 'AT_RISK' | 'BROKEN';

export interface VitalityStreak {
  id: string;
  userId: string;
  currentStreakDays: number;
  longestStreakDays: number;
  lastCheckInOn: string | null;
  streakStartedOn: string | null;
  graceWindowEndsOn: string | null;
  status: VitalityStreakStatus;
  createdAt: string;
  updatedAt: string;
}

export type SocialConnectionStatus = 'PENDING' | 'ACCEPTED' | 'DECLINED';

export interface SocialConnection {
  id: string;
  requesterUserId: string;
  requesterDisplayName: string;
  addresseeUserId: string;
  addresseeDisplayName: string;
  status: SocialConnectionStatus;
  respondedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export type SocialFeedPostType =
  | 'scan_share'
  | 'streak_milestone'
  | 'connection_joined'
  | 'reflection_note';

export type SocialFeedAudience =
  | 'connections'
  | 'selected_connections'
  | 'private';

export type SocialFeedScope = 'all' | 'connections' | 'self';

export type SocialFeedReactionType =
  | 'acknowledge'
  | 'celebrate'
  | 'support';

export type SocialFeedTone =
  | 'sage'
  | 'sunset'
  | 'cream'
  | 'mist'
  | 'neutral';

export type SocialFeedShareMode = 'summary_only' | 'selected_metrics';

export type SocialFeedMetricKey =
  | 'hrBpm'
  | 'hrvMs'
  | 'respiratoryRate'
  | 'spo2'
  | 'stiffnessIndex'
  | 'qualityScore';

export interface SocialFeedUserPreview {
  id: string;
  displayName: string;
  avatarUrl: string | null;
}

export interface SocialCircleMemberPreview extends SocialFeedUserPreview {
  lastActivityAt: string | null;
}

export interface SocialCircleSummary {
  activeConnectionCount: number;
  pendingInviteCount: number;
  unreadFeedCount: number;
  latestActivityAt: string | null;
  membersPreview: SocialCircleMemberPreview[];
}

export interface SocialFeedMetric {
  key: SocialFeedMetricKey;
  label: string;
  value: string;
  unit: string | null;
}

export interface SocialFeedReactionSummary {
  reactionType: SocialFeedReactionType;
  count: number;
  reactedByViewer: boolean;
}

export interface SocialFeedViewerState {
  canReact: boolean;
  canComment: boolean;
  canDelete: boolean;
  canEdit: boolean;
}

export interface SocialFeedComment {
  id: string;
  author: SocialFeedUserPreview;
  text: string;
  createdAt: string;
  updatedAt: string;
}

export interface SocialFeedPostSource {
  sessionId: string | null;
  scanType: ScanType | null;
  sharedAt: string | null;
}

export interface SocialFeedPostDisplay {
  tone: SocialFeedTone;
  headline: string;
  body: string;
  sharedMetrics: SocialFeedMetric[];
}

export interface SocialFeedPost {
  id: string;
  postType: SocialFeedPostType;
  audience: SocialFeedAudience;
  author: SocialFeedUserPreview;
  source: SocialFeedPostSource;
  display: SocialFeedPostDisplay;
  reactionSummary: SocialFeedReactionSummary[];
  commentCount: number;
  latestComments: SocialFeedComment[];
  viewerState: SocialFeedViewerState;
  createdAt: string;
  updatedAt: string;
}

export interface SocialFeedPage {
  items: SocialFeedPost[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface SocialFeedCommentsPage {
  items: SocialFeedComment[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface CreateSocialFeedPostPayload {
  postType: Extract<SocialFeedPostType, 'scan_share' | 'reflection_note'>;
  audience: SocialFeedAudience;
  sessionId?: string;
  text?: string;
  shareMode?: SocialFeedShareMode;
  sharedMetricKeys?: SocialFeedMetricKey[];
  targetConnectionIds?: string[];
}

export interface SocialFeedReactionPayload {
  reactionType: SocialFeedReactionType;
}

export interface SocialFeedCommentPayload {
  text: string;
}

export interface SocialFeedPreferences {
  defaultShareAudience: SocialFeedAudience;
  defaultShareMode: SocialFeedShareMode;
  allowComments: boolean;
  allowReactions: boolean;
  autoShareMilestones: boolean;
}

export interface SocialDiscoveryUser extends SocialFeedUserPreview {
  connectionStatus: SocialConnectionStatus | null;
}

export interface SocialFeedReadMarkerPayload {
  lastSeenPostId: string;
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
