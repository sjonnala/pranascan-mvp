package com.pranapulse.core.feedback.domain;

import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.scan.domain.ScanSession;
import com.pranapulse.core.shared.persistence.AuditableEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.Objects;

@Entity
@Table(
        schema = "core",
        name = "scan_feedback",
        indexes = {
                @Index(name = "idx_scan_feedback_user_id", columnList = "user_id")
        },
        uniqueConstraints = {
                @UniqueConstraint(name = "uk_scan_feedback_session_id", columnNames = "session_id")
        }
)
public class ScanFeedback extends AuditableEntity {

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "session_id", nullable = false)
    private ScanSession session;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "useful_response", nullable = false, length = 16)
    private String usefulResponse;

    @Column(name = "nps_score")
    private Integer npsScore;

    @Column(name = "comment", length = 500)
    private String comment;

    protected ScanFeedback() {
    }

    public ScanFeedback(
            ScanSession session,
            User user,
            String usefulResponse,
            Integer npsScore,
            String comment
    ) {
        this.session = Objects.requireNonNull(session, "session must not be null");
        this.user = Objects.requireNonNull(user, "user must not be null");
        this.usefulResponse = normalizeUsefulResponse(usefulResponse);
        this.npsScore = npsScore;
        this.comment = normalizeComment(comment);
    }

    public ScanSession getSession() {
        return session;
    }

    public User getUser() {
        return user;
    }

    public String getUsefulResponse() {
        return usefulResponse;
    }

    public Integer getNpsScore() {
        return npsScore;
    }

    public String getComment() {
        return comment;
    }

    private static String normalizeUsefulResponse(String usefulResponse) {
        String normalized = Objects.requireNonNull(usefulResponse, "usefulResponse must not be null").trim();
        if (!normalized.equals("useful") && !normalized.equals("needs_work")) {
            throw new IllegalArgumentException("usefulResponse must be 'useful' or 'needs_work'.");
        }
        return normalized;
    }

    private static String normalizeComment(String comment) {
        if (comment == null) {
            return null;
        }
        String trimmed = comment.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
