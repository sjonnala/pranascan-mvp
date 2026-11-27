/**
 * Scan contract revision 2 value objects (T-401 audit, T-403).
 *
 * <p>Typed, invariant-checked replacements for the {@code key:value} diagnostics that rev-1
 * intelligence packs into {@code flags}. They mirror {@code scan_intelligence.proto} rev 2 and
 * the V8 Flyway columns. Every enum has an {@code UNKNOWN}/{@code UNSPECIFIED} value so that
 * "the peer did not say" never reads as "measured" or "applicable".
 *
 * <p>Wellness indicators only: nothing in this package names, implies or rules out a medical
 * condition (see {@link com.pranapulse.core.scan.domain.contract.WellnessWording}).
 *
 * <p>Deliberately free of Spring/JPA dependencies; entities, the gRPC gateway and REST DTOs are
 * not wired to these types yet, so this package changes no runtime behaviour.
 */
package com.pranapulse.core.scan.domain.contract;
