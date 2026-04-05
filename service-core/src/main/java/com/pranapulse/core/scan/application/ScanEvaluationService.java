package com.pranapulse.core.scan.application;

import org.springframework.stereotype.Service;

@Service
public class ScanEvaluationService {

    private final IntelligenceServiceGateway intelligenceServiceGateway;

    public ScanEvaluationService(IntelligenceServiceGateway intelligenceServiceGateway) {
        this.intelligenceServiceGateway = intelligenceServiceGateway;
    }

    public ScanEvaluationOutcome evaluate(ScanEvaluationCommand command) {
        return intelligenceServiceGateway.evaluate(command);
    }
}
