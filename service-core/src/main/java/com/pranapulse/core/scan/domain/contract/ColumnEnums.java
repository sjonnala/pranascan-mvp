package com.pranapulse.core.scan.domain.contract;

import java.util.Locale;

/** Shared helpers for enums persisted as VARCHAR names, where NULL means "unknown". */
final class ColumnEnums {

    private ColumnEnums() {
    }

    static <E extends Enum<E>> E fromColumn(Class<E> type, String column, E unknown) {
        if (column == null || column.isBlank()) {
            return unknown;
        }
        try {
            return Enum.valueOf(type, column.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            return unknown;
        }
    }

    static <E extends Enum<E>> String toColumn(E value, E unknown) {
        return value == null || value == unknown ? null : value.name();
    }
}
