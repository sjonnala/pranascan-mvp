"""Reference adapters: contact PPG/ECG waveform -> validator reference CSV (gaps G2, G3).

Every public rPPG dataset ships a reference *waveform*, while
``scripts/validate_accuracy.py::load_ecg_gold`` wants rows of
``timestamp_ms, hr_bpm, hrv_rmssd_ms``. This module bridges the two.

Alignment with the validator
----------------------------
The validator normalises the trace and the reference CSV to their own first
timestamp, then averages every reference row whose ``timestamp_ms`` falls in each
half-open window ``[k * stride, k * stride + window)``. So the adapter:

1. emits rows on a uniform grid (``grid_s``, default 1 s) whose **first row sits
   exactly at the trace origin** (``origin_s``, default the waveform start), so the
   two independent normalisations line up;
2. gives each row the HR interpolated from the beat-to-beat series at that time,
   so the validator's window mean equals the time-averaged reference HR of that
   window;
3. gives each row the RMSSD of the beats inside a ``window_s`` window centred on
   it, matching the validator's window length.

``reference_window_summary`` computes the exact per-window HR and RMSSD on the
validator's grid, for checks and reports.

HRV note: prefer ECG. Finger-PPG RMSSD is inflated by pulse-arrival jitter.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import signal

from .dataset_model import REFERENCE_KINDS

VALIDATOR_WINDOW_S = 10.0
VALIDATOR_STRIDE_S = 5.0
MIN_IBI_S = 0.25  # 240 bpm
DOMINANT_PERIOD_FRACTION = 0.6
RELATIVE_PROMINENCE_FLOOR = 0.4
MAX_IBI_S = 1.5  # 40 bpm
PPG_BAND_HZ = (0.7, 4.0)
ECG_BAND_HZ = (5.0, 30.0)
REFERENCE_FIELDNAMES = ("timestamp_ms", "hr_bpm", "hrv_rmssd_ms")


@dataclass(frozen=True)
class BeatSeries:
    """Detected beat times (seconds) from a reference waveform."""

    beat_times_s: np.ndarray
    kind: str
    sample_rate_hz: float

    @property
    def ibi_s(self) -> np.ndarray:
        return np.diff(self.beat_times_s)


@dataclass(frozen=True)
class ReferenceWindow:
    """Reference values for one validator window."""

    start_ms: float
    end_ms: float
    hr_bpm: float | None
    hrv_rmssd_ms: float | None
    beat_count: int


def detect_beats(
    t_s: Sequence[float] | np.ndarray,
    waveform: Sequence[float] | np.ndarray,
    kind: str = "ppg_waveform",
) -> BeatSeries:
    """Detect beats in a PPG (systolic peaks) or ECG (R peaks) waveform.

    The waveform may be irregularly sampled; it is resampled onto a uniform grid at
    its median rate first. Peak times are refined with parabolic interpolation, which
    matters for RMSSD at low reference rates (MMPD's PPG is 30 Hz).
    """
    if kind not in REFERENCE_KINDS or kind == "hr_series":
        raise ValueError("kind must be 'ppg_waveform' or 'ecg_waveform'.")
    t = np.asarray(t_s, dtype=np.float64)
    x = np.asarray(waveform, dtype=np.float64)
    if t.ndim != 1 or t.shape != x.shape:
        raise ValueError("t_s and waveform must be 1-D arrays of equal length.")
    finite = np.isfinite(t) & np.isfinite(x)
    t, x = t[finite], x[finite]
    order = np.argsort(t, kind="stable")
    t, x = t[order], x[order]
    keep = np.concatenate([[True], np.diff(t) > 0])
    t, x = t[keep], x[keep]
    if t.size < 16:
        raise ValueError("Reference waveform is too short.")

    fs = 1.0 / float(np.median(np.diff(t)))
    grid = t[0] + np.arange(int(math.floor((t[-1] - t[0]) * fs)) + 1) / fs
    y = np.interp(grid, t, x)

    low_hz, high_hz = PPG_BAND_HZ if kind == "ppg_waveform" else ECG_BAND_HZ
    nyquist = fs / 2.0
    high_hz = min(high_hz, 0.9 * nyquist)
    if low_hz >= high_hz:
        raise ValueError(f"Sample rate {fs:.1f} Hz is too low for a {kind} reference.")
    sos = signal.butter(3, [low_hz / nyquist, high_hz / nyquist], btype="band", output="sos")
    filtered = signal.sosfiltfilt(sos, y - np.mean(y))
    # ECG R peaks may be negative-going depending on lead placement.
    if kind == "ecg_waveform" and abs(float(np.min(filtered))) > abs(float(np.max(filtered))):
        filtered = -filtered

    # A PPG's dicrotic wave sits ~0.3 s after the systolic peak, inside the 0.25 s
    # minimum IBI at low heart rates. Space peaks by a fraction of the dominant period
    # so the dicrotic bump is never counted as a beat.
    # ECG R peaks are narrow and the ECG band removes the fundamental, so ECG keeps the
    # plain minimum-IBI spacing.
    min_spacing_s = MIN_IBI_S
    if kind == "ppg_waveform":
        dominant_hz = _dominant_frequency_hz(filtered, fs, low_hz, high_hz)
        min_spacing_s = max(MIN_IBI_S, DOMINANT_PERIOD_FRACTION / dominant_hz)
    distance = max(1, int(min_spacing_s * fs))
    prominence = max(float(np.std(filtered)) * 0.3, 1e-12)
    peaks, properties = signal.find_peaks(filtered, distance=distance, prominence=prominence)
    if peaks.size >= 3:
        # A dicrotic bump or a filter edge leaves a peak far weaker than real beats,
        # e.g. after the last beat where no stronger neighbour suppresses it.
        prominences = properties["prominences"]
        peaks = peaks[prominences >= RELATIVE_PROMINENCE_FLOOR * float(np.median(prominences))]
    beat_times = np.array([_parabolic_peak_time(filtered, p, grid, fs) for p in peaks])
    return BeatSeries(beat_times_s=beat_times, kind=kind, sample_rate_hz=fs)


def _dominant_frequency_hz(y: np.ndarray, fs: float, low_hz: float, high_hz: float) -> float:
    """Strongest frequency of ``y`` inside ``[low_hz, high_hz]`` (Welch periodogram)."""
    nperseg = int(min(y.size, max(16, round(8.0 * fs))))
    freqs, power = signal.welch(y, fs=fs, nperseg=nperseg)
    band = (freqs >= low_hz) & (freqs <= high_hz)
    if not np.any(band) or float(np.max(power[band])) <= 0.0:
        return 1.0 / MAX_IBI_S
    return float(freqs[band][int(np.argmax(power[band]))])


def _parabolic_peak_time(y: np.ndarray, index: int, grid: np.ndarray, fs: float) -> float:
    if index <= 0 or index >= y.size - 1:
        return float(grid[index])
    left, centre, right = y[index - 1], y[index], y[index + 1]
    denominator = left - 2.0 * centre + right
    offset = 0.0 if abs(denominator) < 1e-15 else 0.5 * (left - right) / denominator
    return float(grid[index] + np.clip(offset, -0.5, 0.5) / fs)


def _valid_ibis(beat_times_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """IBIs inside the physiological guard, with their midpoint times."""
    ibi = np.diff(beat_times_s)
    mids = beat_times_s[:-1] + ibi / 2.0
    mask = (ibi >= MIN_IBI_S) & (ibi <= MAX_IBI_S)
    return ibi[mask], mids[mask]


def _rmssd_ms(beat_times_s: np.ndarray) -> float | None:
    ibi = np.diff(beat_times_s)
    if ibi.size < 3:
        return None
    # Successive differences only between physiologically valid neighbours.
    valid = (ibi >= MIN_IBI_S) & (ibi <= MAX_IBI_S)
    pairs = valid[1:] & valid[:-1]
    diffs = np.diff(ibi * 1000.0)[pairs]
    if diffs.size < 2:
        return None
    return round(float(np.sqrt(np.mean(diffs**2))), 2)


def beats_to_reference_rows(
    beats: BeatSeries,
    *,
    origin_s: float | None = None,
    end_s: float | None = None,
    grid_s: float = 1.0,
    window_s: float = VALIDATOR_WINDOW_S,
) -> list[dict[str, float | None]]:
    """Grid rows ``{timestamp_ms, hr_bpm, hrv_rmssd_ms}`` aligned to the validator."""
    if grid_s <= 0 or window_s <= 0:
        raise ValueError("grid_s and window_s must be positive.")
    beat_times = np.asarray(beats.beat_times_s, dtype=np.float64)
    ibi, mids = _valid_ibis(beat_times)
    if ibi.size < 2:
        return []
    start = float(beat_times[0]) if origin_s is None else float(origin_s)
    stop = float(beat_times[-1]) if end_s is None else float(end_s)
    instantaneous_hr = 60.0 / ibi

    rows: list[dict[str, float | None]] = []
    n_rows = int(math.floor((stop - start) / grid_s + 1e-9)) + 1
    half = window_s / 2.0
    for index in range(max(n_rows, 0)):
        t = start + index * grid_s
        hr = float(np.interp(t, mids, instantaneous_hr))
        local = beat_times[(beat_times >= t - half) & (beat_times < t + half)]
        rows.append(
            {
                "timestamp_ms": round(t * 1000.0, 3),
                "hr_bpm": round(hr, 2),
                "hrv_rmssd_ms": _rmssd_ms(local),
            }
        )
    return rows


def waveform_to_reference_rows(
    t_s: Sequence[float] | np.ndarray,
    waveform: Sequence[float] | np.ndarray,
    kind: str = "ppg_waveform",
    *,
    origin_s: float | None = None,
    end_s: float | None = None,
    grid_s: float = 1.0,
    window_s: float = VALIDATOR_WINDOW_S,
) -> list[dict[str, float | None]]:
    """PPG/ECG waveform -> validator reference rows (see module docstring)."""
    t = np.asarray(t_s, dtype=np.float64)
    beats = detect_beats(t, waveform, kind)
    return beats_to_reference_rows(
        beats,
        origin_s=float(np.min(t)) if origin_s is None else origin_s,
        end_s=float(np.max(t)) if end_s is None else end_s,
        grid_s=grid_s,
        window_s=window_s,
    )


def reference_window_summary(
    beats: BeatSeries,
    *,
    origin_s: float,
    end_s: float,
    window_s: float = VALIDATOR_WINDOW_S,
    stride_s: float = VALIDATOR_STRIDE_S,
) -> list[ReferenceWindow]:
    """Exact reference HR/RMSSD on the validator's window grid, relative to ``origin_s``."""
    beat_times = np.asarray(beats.beat_times_s, dtype=np.float64)
    windows: list[ReferenceWindow] = []
    start = 0.0
    duration = end_s - origin_s
    while start + window_s <= duration + 1e-6:
        lo, hi = origin_s + start, origin_s + start + window_s
        local = beat_times[(beat_times >= lo) & (beat_times < hi)]
        ibi, _ = _valid_ibis(local)
        hr = round(60.0 / float(np.mean(ibi)), 2) if ibi.size >= 2 else None
        windows.append(
            ReferenceWindow(
                start_ms=round(start * 1000.0, 3),
                end_ms=round((start + window_s) * 1000.0, 3),
                hr_bpm=hr,
                hrv_rmssd_ms=_rmssd_ms(local),
                beat_count=int(local.size),
            )
        )
        start += stride_s
    return windows


def write_reference_csv(path: str | Path, rows: Sequence[dict[str, float | None]]) -> None:
    """Write rows in the exact column layout ``load_ecg_gold`` reads."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REFERENCE_FIELDNAMES))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: ("" if row.get(key) is None else row[key]) for key in REFERENCE_FIELDNAMES}
            )


# ---------------------------------------------------------------------------
# Loaders for common dataset reference formats ([U]: verify on the real files)
# ---------------------------------------------------------------------------


def load_waveform_csv(
    path: str | Path,
    time_column: str,
    value_column: str,
    time_unit_s: float = 1e-3,
) -> tuple[np.ndarray, np.ndarray]:
    """Generic CSV waveform. ``time_unit_s`` converts the time column to seconds."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [(float(r[time_column]), float(r[value_column])) for r in reader]
    if not rows:
        raise ValueError(f"Waveform CSV is empty: {path}")
    array = np.asarray(rows, dtype=np.float64)
    return array[:, 0] * time_unit_s, array[:, 1]


def load_ubfc_ground_truth(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """UBFC-rPPG Dataset 2 ``ground_truth.txt``: row 1 PPG, row 2 HR, row 3 time (s) [U]."""
    lines = [line for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 3:
        raise ValueError("Expected three rows (PPG, HR, time) in UBFC ground_truth.txt.")
    ppg = np.array([float(v) for v in lines[0].split()], dtype=np.float64)
    t_s = np.array([float(v) for v in lines[2].split()], dtype=np.float64)
    if ppg.shape != t_s.shape:
        raise ValueError("UBFC PPG and time rows differ in length.")
    return t_s, ppg


def load_pure_json(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """PURE JSON: ``/FullPackage[*].Value.waveform`` with ``Timestamp`` in ns [U]."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    package = payload.get("/FullPackage") or payload.get("FullPackage")
    if not package:
        raise ValueError("PURE JSON has no '/FullPackage' list.")
    t_s = np.array([float(item["Timestamp"]) * 1e-9 for item in package], dtype=np.float64)
    ppg = np.array([float(item["Value"]["waveform"]) for item in package], dtype=np.float64)
    return t_s, ppg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--format", choices=["csv", "ubfc", "pure"], default="csv")
    parser.add_argument("--kind", choices=["ppg_waveform", "ecg_waveform"], default="ppg_waveform")
    parser.add_argument("--time-column", default="t_ms")
    parser.add_argument("--value-column", default="ppg")
    parser.add_argument("--time-unit-s", type=float, default=1e-3)
    parser.add_argument(
        "--origin-s",
        type=float,
        default=None,
        help="Trace start time in the reference clock (default: waveform start)",
    )
    parser.add_argument("--grid-s", type=float, default=1.0)
    parser.add_argument("--window-s", type=float, default=VALIDATOR_WINDOW_S)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.format == "ubfc":
        t_s, waveform = load_ubfc_ground_truth(args.input)
    elif args.format == "pure":
        t_s, waveform = load_pure_json(args.input)
    else:
        t_s, waveform = load_waveform_csv(
            args.input, args.time_column, args.value_column, args.time_unit_s
        )
    rows = waveform_to_reference_rows(
        t_s,
        waveform,
        args.kind,
        origin_s=args.origin_s,
        grid_s=args.grid_s,
        window_s=args.window_s,
    )
    write_reference_csv(args.output, rows)
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
