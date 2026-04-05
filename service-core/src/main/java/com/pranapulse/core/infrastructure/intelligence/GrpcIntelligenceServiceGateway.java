package com.pranapulse.core.infrastructure.intelligence;

import com.google.protobuf.ByteString;
import com.pranapulse.core.scan.application.IntelligenceServiceGateway;
import com.pranapulse.core.scan.application.ScanEvaluationCommand;
import com.pranapulse.core.scan.application.ScanEvaluationOutcome;
import com.pranapulse.intelligence.grpc.scan.v1.FrameSample;
import com.pranapulse.intelligence.grpc.scan.v1.ScanEvaluationRequest;
import com.pranapulse.intelligence.grpc.scan.v1.ScanEvaluationResponse;
import com.pranapulse.intelligence.grpc.scan.v1.ScanIntelligenceServiceGrpc;
import io.grpc.StatusRuntimeException;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class GrpcIntelligenceServiceGateway implements IntelligenceServiceGateway {

    private final ScanIntelligenceServiceGrpc.ScanIntelligenceServiceBlockingStub scanIntelligenceServiceBlockingStub;

    public GrpcIntelligenceServiceGateway(
            ScanIntelligenceServiceGrpc.ScanIntelligenceServiceBlockingStub scanIntelligenceServiceBlockingStub
    ) {
        this.scanIntelligenceServiceBlockingStub = scanIntelligenceServiceBlockingStub;
    }

    @Override
    public ScanEvaluationOutcome evaluate(ScanEvaluationCommand command) {
        ScanEvaluationResponse response;
        try {
            response = scanIntelligenceServiceBlockingStub
                    .withDeadlineAfter(5, TimeUnit.SECONDS)
                    .evaluateScan(toGrpcRequest(command));
        } catch (StatusRuntimeException ex) {
            throw new IllegalStateException("Failed to reach service-intelligence gRPC.", ex);
        }

        return toOutcome(response);
    }

    private static ScanEvaluationRequest toGrpcRequest(ScanEvaluationCommand command) {
        ScanEvaluationRequest.Builder builder = ScanEvaluationRequest.newBuilder()
                .setQualityScore(command.qualityScore())
                .addAllAudioSamples(command.audioSamples() != null ? command.audioSamples() : List.of())
                .addAllFlags(command.flags());

        if (command.frameData() != null) {
            builder.addAllFrameData(command.frameData().stream()
                    .map(frame -> FrameSample.newBuilder()
                            .setTMs(frame.tMs())
                            .setRMean(frame.rMean())
                            .setGMean(frame.gMean())
                            .setBMean(frame.bMean())
                            .build())
                    .toList());
        }

        if (command.imageBytes() != null && command.imageBytes().length > 0) {
            builder.setImageBytes(ByteString.copyFrom(command.imageBytes()));
        } else if (command.videoBytes() != null && command.videoBytes().length > 0) {
            builder.setVideoBytes(ByteString.copyFrom(command.videoBytes()));
        }

        if (command.hrBpm() != null) {
            builder.setHrBpm(command.hrBpm());
        }
        if (command.hrvMs() != null) {
            builder.setHrvMs(command.hrvMs());
        }
        if (command.respiratoryRate() != null) {
            builder.setRespiratoryRate(command.respiratoryRate());
        }
        if (command.voiceJitterPct() != null) {
            builder.setVoiceJitterPct(command.voiceJitterPct());
        }
        if (command.voiceShimmerPct() != null) {
            builder.setVoiceShimmerPct(command.voiceShimmerPct());
        }
        if (command.lightingScore() != null) {
            builder.setLightingScore(command.lightingScore());
        }
        if (command.motionScore() != null) {
            builder.setMotionScore(command.motionScore());
        }
        if (command.faceConfidence() != null) {
            builder.setFaceConfidence(command.faceConfidence());
        }
        if (command.audioSnrDb() != null) {
            builder.setAudioSnrDb(command.audioSnrDb());
        }
        if (command.frameRMean() != null) {
            builder.setFrameRMean(command.frameRMean());
        }
        if (command.frameGMean() != null) {
            builder.setFrameGMean(command.frameGMean());
        }
        if (command.frameBMean() != null) {
            builder.setFrameBMean(command.frameBMean());
        }

        return builder.build();
    }

    private static ScanEvaluationOutcome toOutcome(ScanEvaluationResponse response) {
        return new ScanEvaluationOutcome(
                response.hasHrBpm() ? response.getHrBpm() : null,
                response.hasHrvMs() ? response.getHrvMs() : null,
                response.hasSpo2() ? response.getSpo2() : null,
                response.hasRespiratoryRate() ? response.getRespiratoryRate() : null,
                response.hasVoiceJitterPct() ? response.getVoiceJitterPct() : null,
                response.hasVoiceShimmerPct() ? response.getVoiceShimmerPct() : null,
                response.getQualityScore(),
                response.hasLightingScore() ? response.getLightingScore() : null,
                response.hasMotionScore() ? response.getMotionScore() : null,
                response.hasFaceConfidence() ? response.getFaceConfidence() : null,
                response.hasAudioSnrDb() ? response.getAudioSnrDb() : null,
                response.getFlagsList(),
                response.getWarningsList(),
                response.getQualityGatePassed(),
                response.hasRejectionReason() ? response.getRejectionReason() : null,
                response.hasVascularAgeEstimate() ? response.getVascularAgeEstimate() : null,
                response.hasVascularAgeConfidence() ? response.getVascularAgeConfidence() : null,
                response.hasHbProxyScore() ? response.getHbProxyScore() : null,
                response.hasAnemiaWellnessLabel() ? response.getAnemiaWellnessLabel() : null,
                response.hasAnemiaConfidence() ? response.getAnemiaConfidence() : null
        );
    }
}
