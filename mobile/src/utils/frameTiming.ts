/**
 * frameTiming - capture-clock timestamps and delivered-FPS statistics for rPPG traces.
 *
 * Why this exists
 * ---------------
 * The selfie rPPG trace used to be stamped with `Date.now()` on the JS thread, after the
 * worklet-to-JS hop. Any ordinary JS stall (GC, a re-render) queues frame callbacks, which
 * then drain back-to-back with identical millisecond stamps. The backend's
 * `_validate_and_materialize` rejects such traces as `irregular_timestamps`, so one stall
 * can throw away a whole scan on a budget phone.
 *
 * VisionCamera already gives every frame a capture-time timestamp (`frame.timestamp`) from
 * the host clock. Its unit differs by platform in react-native-vision-camera v4:
 *   - Android: CameraX `ImageInfo.getTimestamp()`, in nanoseconds.
 *   - iOS:     `CMTimeGetSeconds(presentationTime) * 1000`, in milliseconds.
 * Rather than trusting the platform, `FrameClock` infers the unit from the first positive
 * inter-frame delta, which is unambiguous for any real camera (see `inferTimestampUnit`).
 *
 * `Date.now()` is kept only as a defensive fallback for frames that carry no usable
 * hardware timestamp (for example some simulators report 0).
 */

import type { CaptureTimingMetadata, FrameTimestampSource } from '../types';

export type { FrameTimestampSource };

export type TimestampUnit = NonNullable<CaptureTimingMetadata['frame_timestamp_unit']>;

const MS_PER_UNIT: Record<TimestampUnit, number> = {
  s: 1_000,
  ms: 1,
  us: 1e-3,
  ns: 1e-6,
};

/**
 * A raw `frame.timestamp` is usable when it is a finite, strictly positive number.
 * Simulators and some HALs report 0 or omit it.
 */
export function isUsableHardwareTimestamp(raw: unknown): raw is number {
  return typeof raw === 'number' && Number.isFinite(raw) && raw > 0;
}

/**
 * Infer the unit of a camera clock from one positive inter-frame delta.
 *
 * Real cameras deliver frames between roughly 1 ms (1000 FPS) and 2 s apart, so the
 * bands below do not overlap:
 *   - delta < 1          → seconds       (a ms/us/ns clock can't tick < 1 unit per frame)
 *   - 1 ≤ delta < 2e3    → milliseconds  (1 ms .. 2 s between frames)
 *   - 2e3 ≤ delta < 1e6  → microseconds  (2 ms .. 1 s between frames)
 *   - delta ≥ 1e6        → nanoseconds   (≥ 1 ms between frames)
 *
 * Returns null for a non-positive or non-finite delta (a duplicate or regressing frame),
 * so the caller can wait for the next frame.
 */
export function inferTimestampUnit(deltaRaw: number): TimestampUnit | null {
  if (!Number.isFinite(deltaRaw) || deltaRaw <= 0) {
    return null;
  }
  if (deltaRaw < 1) {
    return 's';
  }
  if (deltaRaw < 2_000) {
    return 'ms';
  }
  if (deltaRaw < 1_000_000) {
    return 'us';
  }
  return 'ns';
}

/** Convert a raw clock interval to milliseconds. */
export function rawIntervalToMs(deltaRaw: number, unit: TimestampUnit): number {
  return deltaRaw * MS_PER_UNIT[unit];
}

function roundTo(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

/**
 * Turns per-frame raw timestamps into a strictly increasing, scan-relative millisecond
 * timeline that starts at 0.
 *
 * Rules:
 *  - Hardware stamps: t = anchor + (raw - anchorRaw) converted to ms. Raw values are
 *    subtracted before unit conversion, so nanosecond precision survives.
 *  - A hardware stamp that does not move time forward (duplicate or regressing frame) is
 *    dropped: `stamp` returns null and the caller should discard that sample.
 *  - A frame with no usable hardware stamp falls back to the JS wall clock: the elapsed
 *    `Date.now()` time since the last accepted sample, nudged to +1 ms if a stall made it
 *    zero, so the timeline stays strictly increasing.
 *  - When hardware stamps resume after fallback samples, the camera clock keeps its
 *    original anchor if that still moves time forward; otherwise it is re-anchored onto
 *    the current scan time, so the timeline never jumps backwards.
 */
export class FrameClock {
  private unit: TimestampUnit | null = null;
  private anchorRaw: number | null = null;
  private anchorTMs = 0;
  private lastHardwareRaw: number | null = null;
  private lastTMs: number | null = null;
  private lastWallMs: number | null = null;
  private lastSource: 'hardware' | 'wall_clock' | null = null;

  private hardwareCount = 0;
  private fallbackCount = 0;
  private droppedCount = 0;

  /**
   * Stamp one frame.
   *
   * @param rawTimestamp VisionCamera `frame.timestamp`, captured inside the worklet.
   * @param wallNowMs    `Date.now()` on the JS thread, used only for the fallback.
   * @returns scan-relative milliseconds, or null when the frame should be dropped.
   */
  stamp(rawTimestamp: number | null | undefined, wallNowMs: number): number | null {
    let tMs: number;

    if (isUsableHardwareTimestamp(rawTimestamp)) {
      let hardwareTMs: number | null = null;

      if (this.anchorRaw !== null && this.unit === null && this.lastSource === 'hardware') {
        // Second consecutive hardware frame: its delta tells us the clock's unit.
        const inferred = inferTimestampUnit(rawTimestamp - (this.lastHardwareRaw as number));
        if (inferred === null) {
          this.droppedCount += 1;
          return null;
        }
        this.unit = inferred;
      }

      if (this.anchorRaw !== null && this.unit !== null) {
        const candidate = roundTo(
          this.anchorTMs + rawIntervalToMs(rawTimestamp - this.anchorRaw, this.unit),
          3
        );
        if (this.lastTMs === null || candidate > this.lastTMs) {
          hardwareTMs = candidate;
        } else if (this.lastSource === 'hardware') {
          // Duplicate or regressing frame on the hardware clock.
          this.droppedCount += 1;
          return null;
        }
        // Otherwise wall-clock fallback samples ran ahead of the camera clock: re-anchor.
      }

      if (hardwareTMs === null) {
        // First hardware frame, or (re)joining the timeline after fallback samples.
        hardwareTMs = this.continueFromLast(wallNowMs);
        this.anchorRaw = rawTimestamp;
        this.anchorTMs = hardwareTMs;
      }

      tMs = hardwareTMs;
      this.lastHardwareRaw = rawTimestamp;
      this.lastSource = 'hardware';
      this.hardwareCount += 1;
    } else {
      tMs = this.continueFromLast(wallNowMs);
      this.lastSource = 'wall_clock';
      this.fallbackCount += 1;
    }

    this.lastTMs = tMs;
    this.lastWallMs = wallNowMs;
    return tMs;
  }

  /** Scan time for a sample that has no hardware interval to the previous one. */
  private continueFromLast(wallNowMs: number): number {
    if (this.lastTMs === null || this.lastWallMs === null) {
      return 0;
    }
    const candidate = roundTo(this.lastTMs + (wallNowMs - this.lastWallMs), 3);
    return candidate > this.lastTMs ? candidate : this.lastTMs + 1;
  }

  get timestampSource(): FrameTimestampSource | null {
    if (this.hardwareCount === 0 && this.fallbackCount === 0) {
      return null;
    }
    if (this.fallbackCount === 0) {
      return 'hardware';
    }
    if (this.hardwareCount === 0) {
      return 'wall_clock';
    }
    return 'mixed';
  }

  get timestampUnit(): TimestampUnit | null {
    return this.unit;
  }

  get hardwareSampleCount(): number {
    return this.hardwareCount;
  }

  get fallbackSampleCount(): number {
    return this.fallbackCount;
  }

  get droppedSampleCount(): number {
    return this.droppedCount;
  }
}

export interface FrameRateStats {
  /** Frames per second actually delivered to the trace: (n - 1) / span. */
  delivered_fps: number | null;
  /** Population standard deviation of inter-frame intervals, in ms. */
  fps_jitter_ms: number | null;
  /** Mean inter-frame interval, in ms. */
  mean_frame_interval_ms: number | null;
}

/**
 * Delivered frame rate and jitter from a scan-relative timestamp series.
 *
 * `delivered_fps` needs at least 2 samples spanning a positive time; `fps_jitter_ms`
 * needs at least 2 intervals. Values are rounded to 2 decimals.
 */
export function computeFrameRateStats(timestampsMs: readonly number[]): FrameRateStats {
  const empty: FrameRateStats = {
    delivered_fps: null,
    fps_jitter_ms: null,
    mean_frame_interval_ms: null,
  };
  if (timestampsMs.length < 2) {
    return empty;
  }

  const spanMs = timestampsMs[timestampsMs.length - 1] - timestampsMs[0];
  if (!(spanMs > 0)) {
    return empty;
  }

  const intervals: number[] = [];
  for (let index = 1; index < timestampsMs.length; index += 1) {
    intervals.push(timestampsMs[index] - timestampsMs[index - 1]);
  }
  const meanInterval = spanMs / intervals.length;

  let jitter: number | null = null;
  if (intervals.length >= 2) {
    const variance =
      intervals.reduce((sum, interval) => sum + (interval - meanInterval) ** 2, 0) /
      intervals.length;
    jitter = roundTo(Math.sqrt(variance), 2);
  }

  return {
    delivered_fps: roundTo((intervals.length * 1_000) / spanMs, 2),
    fps_jitter_ms: jitter,
    mean_frame_interval_ms: roundTo(meanInterval, 2),
  };
}

/** Assemble the CaptureTimingMetadata for a finished scan. */
export function buildCaptureTimingMetadata(
  clock: FrameClock,
  timestampsMs: readonly number[]
): CaptureTimingMetadata {
  const stats = computeFrameRateStats(timestampsMs);
  return {
    delivered_fps: stats.delivered_fps,
    fps_jitter_ms: stats.fps_jitter_ms,
    mean_frame_interval_ms: stats.mean_frame_interval_ms,
    frame_timestamp_source: clock.timestampSource,
    frame_timestamp_unit: clock.timestampUnit,
    hardware_timestamp_count: clock.hardwareSampleCount,
    fallback_timestamp_count: clock.fallbackSampleCount,
    dropped_duplicate_frame_count: clock.droppedSampleCount,
  };
}
