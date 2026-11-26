/**
 * Tests for capture-clock timestamping and delivered-FPS statistics.
 *
 * These cover Critical Issue #2 of the Cycle-1 budget-phone audit: samples stamped with
 * Date.now() on the JS thread collapse to identical milliseconds after a JS stall, and the
 * backend rejects the whole scan as irregular_timestamps.
 */

import {
  computeFrameRateStats,
  FrameClock,
  inferTimestampUnit,
  isUsableHardwareTimestamp,
  rawIntervalToMs,
} from '../src/utils/frameTiming';

const NS_PER_MS = 1_000_000;

/** Monotonic boot-relative clock values, as Android (ns) and iOS (ms) report them. */
const ANDROID_BOOT_NS = 734_215_993_120_456; // ~8.5 days of uptime, in ns
const IOS_BOOT_MS = 734_215_993.120456; // same instant, in ms

function strictlyIncreasing(values: readonly number[]): boolean {
  return values.every((value, index) => index === 0 || value > values[index - 1]);
}

function stampAll(
  clock: FrameClock,
  rawTimestamps: readonly (number | null | undefined)[],
  wallClockMs: readonly number[]
): number[] {
  const stamped: number[] = [];
  rawTimestamps.forEach((raw, index) => {
    const t = clock.stamp(raw, wallClockMs[index]);
    if (t !== null) {
      stamped.push(t);
    }
  });
  return stamped;
}

/** Deterministic pseudo-random sequence so tests never flake. */
function makeRng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1_664_525 + 1_013_904_223) >>> 0;
    return state / 2 ** 32;
  };
}

describe('isUsableHardwareTimestamp', () => {
  it.each([
    [123.4, true],
    [ANDROID_BOOT_NS, true],
    [0, false],
    [-5, false],
    [Number.NaN, false],
    [Number.POSITIVE_INFINITY, false],
    [undefined, false],
    [null, false],
    ['123', false],
  ])('%p -> %p', (raw, expected) => {
    expect(isUsableHardwareTimestamp(raw)).toBe(expected);
  });
});

describe('inferTimestampUnit', () => {
  it('reads a 30 FPS delta in each unit correctly', () => {
    expect(inferTimestampUnit(0.0333)).toBe('s');
    expect(inferTimestampUnit(33.33)).toBe('ms');
    expect(inferTimestampUnit(33_333)).toBe('us');
    expect(inferTimestampUnit(33_333_333)).toBe('ns');
  });

  it('keeps budget-phone rates (12-20 FPS) and short drops in the right unit', () => {
    // 12 FPS = 83.3 ms; a 3-frame drop at 12 FPS = 333 ms.
    expect(inferTimestampUnit(83.3)).toBe('ms');
    expect(inferTimestampUnit(333)).toBe('ms');
    expect(inferTimestampUnit(83_333_333)).toBe('ns');
    expect(inferTimestampUnit(333_333_333)).toBe('ns');
    // High-speed capture: 240 FPS.
    expect(inferTimestampUnit(4.17)).toBe('ms');
    expect(inferTimestampUnit(4_166_667)).toBe('ns');
  });

  it('returns null for duplicate, regressing or non-finite deltas', () => {
    expect(inferTimestampUnit(0)).toBeNull();
    expect(inferTimestampUnit(-33)).toBeNull();
    expect(inferTimestampUnit(Number.NaN)).toBeNull();
  });

  it('converts raw intervals to milliseconds', () => {
    expect(rawIntervalToMs(33_333_333, 'ns')).toBeCloseTo(33.333333, 6);
    expect(rawIntervalToMs(33_333, 'us')).toBeCloseTo(33.333, 6);
    expect(rawIntervalToMs(33.5, 'ms')).toBe(33.5);
    expect(rawIntervalToMs(0.05, 's')).toBeCloseTo(50, 6);
  });
});

describe('FrameClock hardware-timestamp normalisation', () => {
  it('normalises Android nanosecond stamps to scan-relative milliseconds', () => {
    const clock = new FrameClock();
    const raw = [0, 1, 2, 3].map((i) => ANDROID_BOOT_NS + i * 33_333_333);
    const stamped = stampAll(clock, raw, [1000, 1000, 1000, 1000]);

    expect(stamped[0]).toBe(0);
    expect(stamped[1]).toBeCloseTo(33.333, 3);
    expect(stamped[3]).toBeCloseTo(100, 3);
    expect(clock.timestampUnit).toBe('ns');
    expect(clock.timestampSource).toBe('hardware');
  });

  it('normalises iOS millisecond stamps to scan-relative milliseconds', () => {
    const clock = new FrameClock();
    const raw = [0, 1, 2, 3].map((i) => IOS_BOOT_MS + i * 33.333333);
    const stamped = stampAll(clock, raw, [5, 5, 5, 5]);

    expect(stamped[0]).toBe(0);
    expect(stamped[1]).toBeCloseTo(33.333, 3);
    expect(stamped[3]).toBeCloseTo(100, 3);
    expect(clock.timestampUnit).toBe('ms');
  });

  it('gives the same timeline for the same capture whichever unit the platform uses', () => {
    const offsetsMs = [0, 41.7, 108.3, 150.0, 216.7, 258.3];
    const fromNs = stampAll(
      new FrameClock(),
      offsetsMs.map((ms) => ANDROID_BOOT_NS + Math.round(ms * NS_PER_MS)),
      offsetsMs.map(() => 0)
    );
    const fromMs = stampAll(
      new FrameClock(),
      offsetsMs.map((ms) => IOS_BOOT_MS + ms),
      offsetsMs.map(() => 0)
    );
    const fromUs = stampAll(
      new FrameClock(),
      offsetsMs.map((ms) => 734_215_993_120 + ms * 1_000),
      offsetsMs.map(() => 0)
    );

    fromNs.forEach((t, i) => {
      expect(t).toBeCloseTo(offsetsMs[i], 2);
      expect(fromMs[i]).toBeCloseTo(offsetsMs[i], 2);
      expect(fromUs[i]).toBeCloseTo(offsetsMs[i], 2);
    });
  });

  it('keeps sub-millisecond precision for large nanosecond values', () => {
    const clock = new FrameClock();
    // 100 days of uptime in ns is still well inside Number.MAX_SAFE_INTEGER.
    const base = 100 * 24 * 3600 * 1e9;
    const stamped = stampAll(clock, [base, base + 16_666_667, base + 33_333_334], [0, 0, 0]);
    expect(stamped).toEqual([0, 16.667, 33.333]);
  });

  it('waits for a positive delta before committing to a unit', () => {
    const clock = new FrameClock();
    expect(clock.stamp(ANDROID_BOOT_NS, 0)).toBe(0);
    // The HAL re-delivers the same frame: dropped, unit still unknown.
    expect(clock.stamp(ANDROID_BOOT_NS, 1)).toBeNull();
    expect(clock.timestampUnit).toBeNull();
    expect(clock.stamp(ANDROID_BOOT_NS + 50_000_000, 2)).toBeCloseTo(50, 3);
    expect(clock.timestampUnit).toBe('ns');
    expect(clock.droppedSampleCount).toBe(1);
  });

  it('drops duplicate and regressing hardware frames instead of emitting them', () => {
    const clock = new FrameClock();
    const raw = [
      IOS_BOOT_MS,
      IOS_BOOT_MS + 50,
      IOS_BOOT_MS + 50, // duplicate
      IOS_BOOT_MS + 40, // regression
      IOS_BOOT_MS + 100,
    ];
    const stamped = stampAll(clock, raw, [0, 0, 0, 0, 0]);

    expect(stamped).toEqual([0, 50, 100]);
    expect(clock.droppedSampleCount).toBe(2);
    expect(clock.hardwareSampleCount).toBe(3);
  });
});

describe('FrameClock under simulated JS-thread stalls', () => {
  /**
   * A 15 FPS camera with jitter, where every ~20th frame triggers a 400 ms JS stall.
   * Queued callbacks then drain in one burst, so the JS wall clock reads the same
   * millisecond for every queued frame (exactly the Date.now() failure mode).
   */
  function simulateStalledCapture(seed: number) {
    const rng = makeRng(seed);
    const hardwareMs: number[] = [];
    let t = 0;
    for (let i = 0; i < 450; i += 1) {
      t += 1000 / 15 + (rng() - 0.5) * 12; // ±6 ms jitter
      hardwareMs.push(t);
    }

    const wallMs: number[] = [];
    let stallUntil = -1;
    hardwareMs.forEach((captureMs, index) => {
      if (index % 20 === 7) {
        stallUntil = captureMs + 400;
      }
      // While stalled, callbacks are delivered when the stall ends, all at once.
      wallMs.push(Math.floor(Math.max(captureMs + 3, stallUntil)));
    });
    return { hardwareMs, wallMs };
  }

  it('the legacy Date.now() stamps would be rejected as irregular', () => {
    const { wallMs } = simulateStalledCapture(42);
    const nonPositiveDiffs = wallMs.filter((t, i) => i > 0 && t - wallMs[i - 1] <= 0).length;
    // service-intelligence rejects a trace with more than one non-positive diff.
    expect(nonPositiveDiffs).toBeGreaterThan(1);
  });

  it('hardware stamps stay strictly increasing and keep true spacing through stalls', () => {
    const { hardwareMs, wallMs } = simulateStalledCapture(42);
    const clock = new FrameClock();
    const raw = hardwareMs.map((ms) => ANDROID_BOOT_NS + Math.round(ms * NS_PER_MS));
    const stamped = stampAll(clock, raw, wallMs);

    expect(stamped).toHaveLength(hardwareMs.length);
    expect(strictlyIncreasing(stamped)).toBe(true);
    stamped.forEach((tMs, i) => {
      expect(tMs).toBeCloseTo(hardwareMs[i] - hardwareMs[0], 2);
    });
    expect(clock.fallbackSampleCount).toBe(0);
  });

  it('wall-clock fallback stays strictly increasing when stalled samples share a millisecond', () => {
    const { wallMs } = simulateStalledCapture(7);
    const clock = new FrameClock();
    const stamped = stampAll(
      clock,
      wallMs.map(() => 0), // simulator: frame.timestamp is always 0
      wallMs
    );

    expect(stamped).toHaveLength(wallMs.length);
    expect(strictlyIncreasing(stamped)).toBe(true);
    expect(stamped[0]).toBe(0);
    expect(clock.timestampSource).toBe('wall_clock');
    expect(clock.timestampUnit).toBeNull();
  });

  it('uses Date.now() only for frames whose hardware stamp is missing', () => {
    const clock = new FrameClock();
    const stamped = stampAll(
      clock,
      [IOS_BOOT_MS, IOS_BOOT_MS + 50, undefined, IOS_BOOT_MS + 150, IOS_BOOT_MS + 200],
      [10_000, 10_000, 10_000, 10_090, 10_090]
    );

    // Missing stamp during a stall -> nudged 1 ms forward; the camera clock then resumes
    // on its own timeline, so the true 150 ms / 200 ms spacing is kept.
    expect(stamped).toEqual([0, 50, 51, 150, 200]);
    expect(strictlyIncreasing(stamped)).toBe(true);
    expect(clock.timestampSource).toBe('mixed');
    expect(clock.fallbackSampleCount).toBe(1);
    expect(clock.hardwareSampleCount).toBe(4);
  });

  it('falls back entirely when the first frames have no hardware stamp', () => {
    const clock = new FrameClock();
    const stamped = stampAll(clock, [0, 0, 0], [500, 533, 566]);
    expect(stamped).toEqual([0, 33, 66]);
    expect(clock.timestampSource).toBe('wall_clock');
  });
});

describe('computeFrameRateStats', () => {
  it('reports 30 FPS and zero jitter for a perfectly regular stream', () => {
    const timestamps = Array.from({ length: 31 }, (_, i) => i * (1000 / 30));
    const stats = computeFrameRateStats(timestamps);
    expect(stats.delivered_fps).toBeCloseTo(30, 2);
    expect(stats.fps_jitter_ms).toBeCloseTo(0, 2);
    expect(stats.mean_frame_interval_ms).toBeCloseTo(33.33, 2);
  });

  it('measures delivered FPS, not the requested FPS, when frames drop', () => {
    // A "30 FPS" format that only delivers every other frame.
    const timestamps = Array.from({ length: 16 }, (_, i) => i * (2000 / 30));
    expect(computeFrameRateStats(timestamps).delivered_fps).toBeCloseTo(15, 2);
  });

  it('computes jitter as the population SD of inter-frame intervals', () => {
    // Intervals: 50, 70, 50, 70 -> mean 60, SD 10.
    const stats = computeFrameRateStats([0, 50, 120, 170, 240]);
    expect(stats.delivered_fps).toBeCloseTo(4000 / 240, 2);
    expect(stats.fps_jitter_ms).toBe(10);
    expect(stats.mean_frame_interval_ms).toBe(60);
  });

  it('reports a budget-phone stream at its true 12-20 FPS rate with jitter', () => {
    const rng = makeRng(3);
    const timestamps = [0];
    for (let i = 0; i < 400; i += 1) {
      const fps = 12 + rng() * 8;
      timestamps.push(timestamps[timestamps.length - 1] + 1000 / fps);
    }
    const stats = computeFrameRateStats(timestamps);
    expect(stats.delivered_fps).toBeGreaterThan(12);
    expect(stats.delivered_fps).toBeLessThan(20);
    expect(stats.fps_jitter_ms).toBeGreaterThan(5);
  });

  it('returns nulls when there is too little data', () => {
    expect(computeFrameRateStats([])).toEqual({
      delivered_fps: null,
      fps_jitter_ms: null,
      mean_frame_interval_ms: null,
    });
    expect(computeFrameRateStats([0]).delivered_fps).toBeNull();
    expect(computeFrameRateStats([5, 5]).delivered_fps).toBeNull();
    const twoSamples = computeFrameRateStats([0, 40]);
    expect(twoSamples.delivered_fps).toBe(25);
    expect(twoSamples.fps_jitter_ms).toBeNull();
  });

  it('stays correct on the output of FrameClock for a stalled capture', () => {
    const clock = new FrameClock();
    const hardwareMs = Array.from({ length: 300 }, (_, i) => i * 62.5); // 16 FPS
    const wallMs = hardwareMs.map((ms, i) => (i >= 100 && i < 110 ? 6_900 : Math.floor(ms)));
    const stamped = stampAll(
      clock,
      hardwareMs.map((ms) => ANDROID_BOOT_NS + ms * NS_PER_MS),
      wallMs
    );
    const stats = computeFrameRateStats(stamped);
    expect(stats.delivered_fps).toBeCloseTo(16, 2);
    expect(stats.fps_jitter_ms).toBeCloseTo(0, 2);
  });
});
