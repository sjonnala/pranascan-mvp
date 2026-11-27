package com.pranapulse.core.scan.domain.contract;

/** Camera auto-exposure / auto-white-balance lock outcome. Names match V8's lock CHECKs. */
public enum LockState {
    CONFIRMED,
    REQUESTED,
    IGNORED,
    UNSUPPORTED,
    UNKNOWN;

    public static LockState fromColumn(String column) {
        return ColumnEnums.fromColumn(LockState.class, column, UNKNOWN);
    }

    public String toColumn() {
        return ColumnEnums.toColumn(this, UNKNOWN);
    }
}
