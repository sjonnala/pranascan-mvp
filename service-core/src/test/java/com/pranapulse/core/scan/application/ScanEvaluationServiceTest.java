package com.pranapulse.core.scan.application;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class ScanEvaluationServiceTest {

    @Test
    void delegatesToIntelligenceGateway() {
        ScanEvaluationOutcome expected = new ScanEvaluationOutcome(
                72.0,
                40.0,
                97.0,
                15.0,
                0.4,
                1.8,
                0.91,
                0.8,
                0.97,
                0.94,
                22.0,
                List.of("borderline_noise"),
                List.of("borderline_noise"),
                true,
                null,
                36.0,
                0.78,
                11.4,
                "monitor",
                0.66
        );
        ScanEvaluationService service = new ScanEvaluationService(command -> expected);

        ScanEvaluationOutcome actual = service.evaluate(new ScanEvaluationCommand(
                null,
                null,
                null,
                null,
                72.0,
                40.0,
                15.0,
                0.4,
                1.8,
                0.91,
                0.8,
                0.97,
                0.94,
                22.0,
                List.of(),
                100.0,
                110.0,
                90.0
        ));

        assertEquals(expected, actual);
    }
}
