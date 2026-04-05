package com.pranapulse.core.scan.domain;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.scan.application.ScanEvaluationOutcome;
import com.pranapulse.core.shared.persistence.AuditableEntity;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToOne;
import jakarta.persistence.OrderColumn;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Entity
@Table(
        schema = "core",
        name = "scan_results",
        indexes = {
                @Index(name = "idx_scan_results_user_id", columnList = "user_id")
        },
        uniqueConstraints = {
                @UniqueConstraint(name = "uk_scan_results_session_id", columnNames = "session_id")
        }
)
public class ScanResult extends AuditableEntity {

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "session_id", nullable = false)
    private ScanSession session;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "hr_bpm")
    private Double hrBpm;

    @Column(name = "hrv_ms")
    private Double hrvMs;

    @Column(name = "spo2")
    private Double spo2;

    @Column(name = "stiffness_index")
    private Double stiffnessIndex;

    @Column(name = "respiratory_rate")
    private Double respiratoryRate;

    @Column(name = "voice_jitter_pct")
    private Double voiceJitterPct;

    @Column(name = "voice_shimmer_pct")
    private Double voiceShimmerPct;

    @Column(name = "quality_score", nullable = false)
    private double qualityScore;

    @Column(name = "lighting_score")
    private Double lightingScore;

    @Column(name = "motion_score")
    private Double motionScore;

    @Column(name = "face_confidence")
    private Double faceConfidence;

    @Column(name = "audio_snr_db")
    private Double audioSnrDb;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(
            schema = "core",
            name = "scan_result_flags",
            joinColumns = @JoinColumn(name = "scan_result_id", nullable = false)
    )
    @OrderColumn(name = "flag_order")
    @Column(name = "flag", nullable = false, length = 64)
    private List<String> flags = new ArrayList<>();

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(
            schema = "core",
            name = "scan_result_warnings",
            joinColumns = @JoinColumn(name = "scan_result_id", nullable = false)
    )
    @OrderColumn(name = "warning_order")
    @Column(name = "warning", nullable = false, length = 64)
    private List<String> warnings = new ArrayList<>();

    @Column(name = "trend_alert", length = 64)
    private String trendAlert;

    @Column(name = "vascular_age_estimate")
    private Double vascularAgeEstimate;

    @Column(name = "vascular_age_confidence")
    private Double vascularAgeConfidence;

    @Column(name = "hb_proxy_score")
    private Double hbProxyScore;

    @Column(name = "anemia_wellness_label", length = 32)
    private String anemiaWellnessLabel;

    @Column(name = "anemia_confidence")
    private Double anemiaConfidence;

    protected ScanResult() {
    }

    public ScanResult(ScanSession session, User user, ScanEvaluationOutcome outcome, String trendAlert) {
        this.session = Objects.requireNonNull(session, "session must not be null");
        this.user = Objects.requireNonNull(user, "user must not be null");
        this.hrBpm = outcome.hrBpm();
        this.hrvMs = outcome.hrvMs();
        this.spo2 = outcome.spo2();
        this.stiffnessIndex = outcome.stiffnessIndex();
        this.respiratoryRate = outcome.respiratoryRate();
        this.voiceJitterPct = outcome.voiceJitterPct();
        this.voiceShimmerPct = outcome.voiceShimmerPct();
        this.qualityScore = outcome.qualityScore();
        this.lightingScore = outcome.lightingScore();
        this.motionScore = outcome.motionScore();
        this.faceConfidence = outcome.faceConfidence();
        this.audioSnrDb = outcome.audioSnrDb();
        this.flags = new ArrayList<>(outcome.flags());
        this.warnings = new ArrayList<>(outcome.warnings());
        this.trendAlert = trendAlert;
        this.vascularAgeEstimate = outcome.vascularAgeEstimate();
        this.vascularAgeConfidence = outcome.vascularAgeConfidence();
        this.hbProxyScore = outcome.hbProxyScore();
        this.anemiaWellnessLabel = outcome.anemiaWellnessLabel();
        this.anemiaConfidence = outcome.anemiaConfidence();
    }

    public ScanSession getSession() {
        return session;
    }

    public User getUser() {
        return user;
    }

    public Double getHrBpm() {
        return hrBpm;
    }

    public Double getHrvMs() {
        return hrvMs;
    }

    public Double getSpo2() {
        return spo2;
    }

    public Double getStiffnessIndex() {
        return stiffnessIndex;
    }

    public Double getRespiratoryRate() {
        return respiratoryRate;
    }

    public Double getVoiceJitterPct() {
        return voiceJitterPct;
    }

    public Double getVoiceShimmerPct() {
        return voiceShimmerPct;
    }

    public double getQualityScore() {
        return qualityScore;
    }

    public Double getLightingScore() {
        return lightingScore;
    }

    public Double getMotionScore() {
        return motionScore;
    }

    public Double getFaceConfidence() {
        return faceConfidence;
    }

    public Double getAudioSnrDb() {
        return audioSnrDb;
    }

    public List<String> getFlags() {
        return List.copyOf(flags);
    }

    public List<String> getWarnings() {
        return List.copyOf(warnings);
    }

    public String getTrendAlert() {
        return trendAlert;
    }

    public Double getVascularAgeEstimate() {
        return vascularAgeEstimate;
    }

    public Double getVascularAgeConfidence() {
        return vascularAgeConfidence;
    }

    public Double getHbProxyScore() {
        return hbProxyScore;
    }

    public String getAnemiaWellnessLabel() {
        return anemiaWellnessLabel;
    }

    public Double getAnemiaConfidence() {
        return anemiaConfidence;
    }
}
