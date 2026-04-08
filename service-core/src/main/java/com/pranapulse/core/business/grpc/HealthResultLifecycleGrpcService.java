package com.pranapulse.core.business.grpc;

import com.google.protobuf.Timestamp;
import com.pranapulse.core.business.application.HealthResultLifecycleService;
import com.pranapulse.core.business.domain.health.HealthResultSnapshot;
import com.pranapulse.core.business.domain.health.HealthResultState;
import com.pranapulse.core.business.domain.health.ResultExpired;
import com.pranapulse.core.business.domain.health.ResultPending;
import com.pranapulse.core.business.domain.health.ResultVerified;
import com.pranapulse.core.grpc.health.v1.EvaluateHealthResultRequest;
import com.pranapulse.core.grpc.health.v1.EvaluateHealthResultResponse;
import com.pranapulse.core.grpc.health.v1.HealthResultLifecycleServiceGrpc.HealthResultLifecycleServiceImplBase;
import com.pranapulse.core.grpc.health.v1.HealthResultStatus;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.time.Instant;
import java.util.UUID;
import net.devh.boot.grpc.server.service.GrpcService;

@GrpcService
public class HealthResultLifecycleGrpcService extends HealthResultLifecycleServiceImplBase {

    private final HealthResultLifecycleService healthResultLifecycleService;

    public HealthResultLifecycleGrpcService(HealthResultLifecycleService healthResultLifecycleService) {
        this.healthResultLifecycleService = healthResultLifecycleService;
    }

    @Override
    public void evaluateHealthResult(
            EvaluateHealthResultRequest request,
            StreamObserver<EvaluateHealthResultResponse> responseObserver
    ) {
        try {
            HealthResultSnapshot snapshot = new HealthResultSnapshot(
                    parseUuid(request.getResultId(), "result_id"),
                    parseUuid(request.getUserId(), "user_id"),
                    requireTimestamp(request.hasRecordedAt(), request.getRecordedAt(), "recorded_at"),
                    requireTimestamp(request.hasExpiresAt(), request.getExpiresAt(), "expires_at"),
                    request.hasVerifiedAt() ? toInstant(request.getVerifiedAt()) : null,
                    normalize(request.getVerifiedBy())
            );

            Instant asOf = request.hasAsOf() ? toInstant(request.getAsOf()) : Instant.now();
            HealthResultState resolved = healthResultLifecycleService.evaluate(snapshot, asOf);

            responseObserver.onNext(toResponse(resolved));
            responseObserver.onCompleted();
        } catch (IllegalArgumentException | IllegalStateException ex) {
            responseObserver.onError(Status.INVALID_ARGUMENT.withDescription(ex.getMessage()).asRuntimeException());
        }
    }

    private static EvaluateHealthResultResponse toResponse(HealthResultState state) {
        EvaluateHealthResultResponse.Builder builder = EvaluateHealthResultResponse.newBuilder()
                .setResultId(state.resultId().toString())
                .setUserId(state.userId().toString())
                .setStatus(toProtoStatus(state))
                .setTerminal(state.terminal())
                .setRecordedAt(toTimestamp(state.recordedAt()))
                .setEffectiveAt(toTimestamp(state.effectiveAt()));

        switch (state) {
            case ResultPending pending ->
                    builder.setExpiresAt(toTimestamp(pending.expiresAt()));
            case ResultVerified verified -> {
                builder.setVerifiedAt(toTimestamp(verified.verifiedAt()));
                builder.setVerifiedBy(verified.verifiedBy());
            }
            case ResultExpired expired -> {
                builder.setExpiresAt(toTimestamp(expired.expiryDeadline()));
                builder.setExpiredAt(toTimestamp(expired.expiredAt()));
                builder.setExpirationReason(expired.reason());
            }
            default -> { /* no additional fields for unknown subtypes */ }
        }

        return builder.build();
    }

    private static HealthResultStatus toProtoStatus(HealthResultState state) {
        return switch (state.status()) {
            case PENDING -> HealthResultStatus.HEALTH_RESULT_STATUS_PENDING;
            case VERIFIED -> HealthResultStatus.HEALTH_RESULT_STATUS_VERIFIED;
            case EXPIRED -> HealthResultStatus.HEALTH_RESULT_STATUS_EXPIRED;
        };
    }

    private static UUID parseUuid(String rawValue, String fieldName) {
        if (rawValue == null || rawValue.isBlank()) {
            throw new IllegalArgumentException(fieldName + " must not be blank.");
        }
        try {
            return UUID.fromString(rawValue.trim());
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(fieldName + " must be a valid UUID.");
        }
    }

    private static Instant requireTimestamp(boolean present, Timestamp timestamp, String fieldName) {
        if (!present) {
            throw new IllegalArgumentException(fieldName + " must be provided.");
        }
        return toInstant(timestamp);
    }

    private static Instant toInstant(Timestamp timestamp) {
        return Instant.ofEpochSecond(timestamp.getSeconds(), timestamp.getNanos());
    }

    private static Timestamp toTimestamp(Instant instant) {
        return Timestamp.newBuilder()
                .setSeconds(instant.getEpochSecond())
                .setNanos(instant.getNano())
                .build();
    }

    private static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
