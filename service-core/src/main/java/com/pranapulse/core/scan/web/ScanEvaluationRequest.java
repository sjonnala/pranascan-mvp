package com.pranapulse.core.scan.web;

import com.pranapulse.core.scan.application.ScanEvaluationCommand;
import com.pranapulse.core.scan.domain.ScanType;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ScanEvaluationRequest(
        ScanType scanType,
        @Size(max = 4000) List<@Valid FrameSampleRequest> frameData,
        @Size(max = 22050) List<Double> audioSamples,
        @Size(min = 128, max = 5_242_880) byte[] imageBytes,
        @Size(min = 128, max = 20_971_520) byte[] videoBytes,
        @DecimalMin("30.0") @DecimalMax("220.0") Double hrBpm,
        @DecimalMin("0.0") @DecimalMax("500.0") Double hrvMs,
        @DecimalMin("4.0") @DecimalMax("60.0") Double respiratoryRate,
        @DecimalMin("0.0") @DecimalMax("100.0") Double voiceJitterPct,
        @DecimalMin("0.0") @DecimalMax("100.0") Double voiceShimmerPct,
        @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double qualityScore,
        @DecimalMin("0.0") @DecimalMax("1.0") Double lightingScore,
        @DecimalMin("0.0") @DecimalMax("1.0") Double motionScore,
        @DecimalMin("0.0") @DecimalMax("1.0") Double faceConfidence,
        Double audioSnrDb,
        List<String> flags,
        @DecimalMin("100.0") @DecimalMax("250.0") Double userHeightCm,
        @DecimalMin("0.0") @DecimalMax("255.0") Double frameRMean,
        @DecimalMin("0.0") @DecimalMax("255.0") Double frameGMean,
        @DecimalMin("0.0") @DecimalMax("255.0") Double frameBMean
) {

    @AssertTrue(message = "Provide either image_bytes or video_bytes, not both.")
    public boolean hasSingleMediaPayload() {
        return imageBytes == null || videoBytes == null;
    }

    public ScanEvaluationCommand toCommand() {
        List<ScanEvaluationCommand.FrameSample> mappedFrameData = frameData == null
                ? null
                : frameData.stream()
                        .map(frame -> new ScanEvaluationCommand.FrameSample(
                                frame.tMs(),
                                frame.rMean(),
                                frame.gMean(),
                                frame.bMean()
                        ))
                        .toList();

        return new ScanEvaluationCommand(
                ScanType.defaultIfNull(scanType),
                mappedFrameData,
                audioSamples,
                imageBytes,
                videoBytes,
                hrBpm,
                hrvMs,
                respiratoryRate,
                voiceJitterPct,
                voiceShimmerPct,
                qualityScore,
                lightingScore,
                motionScore,
                faceConfidence,
                audioSnrDb,
                flags != null ? flags : List.of(),
                userHeightCm,
                frameRMean,
                frameGMean,
                frameBMean
        );
    }

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record FrameSampleRequest(
            @DecimalMin("0.0") double tMs,
            @DecimalMin("0.0") @DecimalMax("255.0") double rMean,
            @DecimalMin("0.0") @DecimalMax("255.0") double gMean,
            @DecimalMin("0.0") @DecimalMax("255.0") double bMean
    ) {
    }
}
