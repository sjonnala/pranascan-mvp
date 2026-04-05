package com.pranapulse.core.scan.application;

import java.util.Arrays;
import java.util.List;

public record ScanEvaluationCommand(
        List<FrameSample> frameData,
        List<Double> audioSamples,
        byte[] imageBytes,
        byte[] videoBytes,
        Double hrBpm,
        Double hrvMs,
        Double respiratoryRate,
        Double voiceJitterPct,
        Double voiceShimmerPct,
        double qualityScore,
        Double lightingScore,
        Double motionScore,
        Double faceConfidence,
        Double audioSnrDb,
        List<String> flags,
        Double frameRMean,
        Double frameGMean,
        Double frameBMean
) {

    public ScanEvaluationCommand {
        flags = flags == null ? List.of() : List.copyOf(flags);
        imageBytes = imageBytes == null ? null : Arrays.copyOf(imageBytes, imageBytes.length);
        videoBytes = videoBytes == null ? null : Arrays.copyOf(videoBytes, videoBytes.length);
    }

    @Override
    public byte[] imageBytes() {
        return imageBytes == null ? null : Arrays.copyOf(imageBytes, imageBytes.length);
    }

    @Override
    public byte[] videoBytes() {
        return videoBytes == null ? null : Arrays.copyOf(videoBytes, videoBytes.length);
    }

    public record FrameSample(
            double tMs,
            double rMean,
            double gMean,
            double bMean
    ) {
    }
}
