package com.pranapulse.core.scan.domain.contract;

/** Which {@code scan_intelligence.proto} revision a peer spoke. Absent on the wire (0) means rev 1. */
public final class ContractRevision {

    public static final int REV_1 = 1;
    public static final int REV_2 = 2;
    public static final int CURRENT = REV_2;

    private ContractRevision() {
    }

    /** Normalises a raw {@code contract_revision} wire value: 0/absent is rev 1. */
    public static int effective(int wireValue) {
        if (wireValue < 0) {
            throw new IllegalArgumentException("contract_revision cannot be negative: " + wireValue);
        }
        return wireValue == 0 ? REV_1 : wireValue;
    }

    public static boolean hasTypedAssessments(int wireValue) {
        return effective(wireValue) >= REV_2;
    }
}
