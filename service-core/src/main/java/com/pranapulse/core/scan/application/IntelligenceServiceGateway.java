package com.pranapulse.core.scan.application;

public interface IntelligenceServiceGateway {

    ScanEvaluationOutcome evaluate(ScanEvaluationCommand command);
}
