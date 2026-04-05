package com.pranapulse.core.business.application;

import com.pranapulse.core.business.domain.health.HealthResultSnapshot;
import com.pranapulse.core.business.domain.health.HealthResultState;
import com.pranapulse.core.business.domain.health.HealthResultStateMachine;
import java.time.Instant;
import org.springframework.stereotype.Service;

@Service
public class HealthResultLifecycleService {

    private final HealthResultStateMachine stateMachine = new HealthResultStateMachine();

    public HealthResultState evaluate(HealthResultSnapshot snapshot, Instant asOf) {
        return stateMachine.resolve(snapshot, asOf);
    }
}
