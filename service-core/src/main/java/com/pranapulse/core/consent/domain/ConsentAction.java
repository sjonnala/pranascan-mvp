package com.pranapulse.core.consent.domain;

public enum ConsentAction {
    GRANTED("granted"),
    REVOKED("revoked"),
    DELETION_REQUESTED("deletion_requested");

    private final String value;

    ConsentAction(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
