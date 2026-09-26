"""Training-only pilot-tone response normalization and delay audit.

The first 20 ms of each dwell defines one fixed complex response per tone.  That
response is then applied, unchanged, to later frames.  The retained common phase
is only a gauge; this module does not identify geometric phase truth.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent / "pilot-cache.npz"


def unit(z: np.ndarray) -> np.ndarray:
    return z / np.maximum(np.abs(z), 1e-30)


def fit_training_response(channel: np.ndarray, train: np.ndarray) -> dict[str, np.ndarray]:
    """Fit fixed relative tone phases from training frames only.

    ``channel`` is [frame, receiver, tone].  Magnitudes weight the circular
    estimate, while response correction is phase-only to avoid inventing SNR.
    """
    z = np.conj(channel[:, 0]) * channel[:, 1]
    tone_mean = np.sum(z[train], axis=0)
    aggregate = np.sum(tone_mean)
    gauge = unit(np.asarray(aggregate)).item()
    response = unit(tone_mean) / gauge
    return {"response": response, "gauge": np.asarray(gauge), "tone_mean": tone_mean}


def apply_response(channel: np.ndarray, calibration: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    z = np.conj(channel[:, 0]) * channel[:, 1]
    corrected = z * np.conj(calibration["response"])[None, :]
    raw_sum = np.sum(z, axis=1)
    normalized_sum = np.sum(corrected, axis=1)
    agreement = np.abs(np.mean(unit(corrected), axis=1))
    return {
        "raw_phase_deg": np.angle(raw_sum, deg=True),
        "normalized_phase_deg": np.angle(normalized_sum, deg=True),
        "tone_agreement": agreement,
        "corrected": corrected,
    }


def delay_audit(tone_mean: np.ndarray, frequencies_hz: np.ndarray) -> dict[str, object]:
    """Return the principal phase-slope delay and its unavoidable tone aliases."""
    order = np.argsort(frequencies_hz)
    f = frequencies_hz[order]
    phase = np.unwrap(np.angle(tone_mean[order]))
    slope, intercept = np.polyfit(f - np.mean(f), phase, 1, w=np.sqrt(np.abs(tone_mean[order])))
    spacing = float(np.median(np.diff(f)))
    principal = float(-slope / (2 * np.pi))
    alias_period = float(1 / spacing)
    return {
        "principal_delay_s": principal,
        "alias_period_s": alias_period,
        "nearby_alias_delays_s": [principal + k * alias_period for k in range(-2, 3)],
        "fit_intercept_rad": float(intercept),
        "warning": "Eight uniformly spaced tones identify delay only modulo 1/tone_spacing.",
    }


def _cache_data(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    d = np.load(path)
    required = {"frame_visit_index", "frame_time_s", "tone_frequency_hz", "h0", "h1",
                "support_start_s", "support_end_s"}
    missing = required.difference(d.files)
    if missing:
        raise KeyError(f"pilot cache missing keys: {sorted(missing)}")
    visits = d["frame_visit_index"].astype(int)
    times = d["frame_time_s"].astype(float)
    # Complete support intervals prevent a frame from straddling the split.
    held = d["support_start_s"].astype(float) >= .020
    channel = np.stack([d["h0"], d["h1"]], axis=1)
    return visits, times, held, d["tone_frequency_hz"].astype(float), channel


def main(cache: Path = CACHE) -> None:
    visits, times, held, frequencies, channel = _cache_data(cache)
    rows, summaries = [], []
    labelled = False
    for visit in np.unique(visits):
        selected = visits == visit
        with np.load(cache) as cached:
            train = selected & (cached["support_end_s"].astype(float) <= .020)
        test = selected & held
        calibration = fit_training_response(channel, train)
        result = apply_response(channel, calibration)
        audit = delay_audit(calibration["tone_mean"], frequencies)
        for i in np.flatnonzero(selected):
            rows.append({"visit_index": int(visit), "time_s": float(times[i]),
                         "held_after_20ms": bool(held[i]),
                         "evaluation_set": "training" if train[i] else ("held" if test[i] else "boundary"),
                         "raw_phase_deg": float(result["raw_phase_deg"][i]),
                         "normalized_phase_deg": float(result["normalized_phase_deg"][i]),
                         "tone_agreement": float(result["tone_agreement"][i])})
        phase_change = np.angle(np.exp(1j*np.radians(result["normalized_phase_deg"][test] - result["raw_phase_deg"][test])), deg=True)
        summaries.append({"visit_index": int(visit), "training_frames": int(train.sum()),
                          "held_frames": int(test.sum()),
                          "held_median_tone_agreement": float(np.median(result["tone_agreement"][test])),
                          "held_raw_to_normalized_wrapped_rms_deg": float(np.sqrt(np.mean(phase_change**2))),
                          "delay_audit": audit,
                          "training_relative_tone_phase_deg": np.angle(calibration["response"], deg=True).tolist()})

    HERE.mkdir(parents=True, exist_ok=True)
    with (HERE / "response-frames.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    (HERE / "response-summary.json").write_text(json.dumps({"cache": str(cache), "cache_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(), "dwells": summaries}, indent=2) + "\n")
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, constrained_layout=True)
    for visit in np.unique(visits):
        rs = [r for r in rows if r["visit_index"] == visit]
        t = np.array([r["time_s"] for r in rs]); h = np.array([r["held_after_20ms"] for r in rs])
        axes[0].plot(t[h], [r["raw_phase_deg"] for r in rs if r["held_after_20ms"]], ".", ms=3, alpha=.55,
                     color="#888888", label="raw tone sum" if not labelled else None)
        axes[0].plot(t[h], [r["normalized_phase_deg"] for r in rs if r["held_after_20ms"]], ".", ms=3, alpha=.75,
                     color="#176d92", label="fixed training normalization" if not labelled else None)
        axes[1].plot(t[h], [r["tone_agreement"] for r in rs if r["held_after_20ms"]], ".", ms=3)
        labelled = True
    axes[0].set(ylabel="RX1 − RX0 phase (deg)", ylim=(-185, 185), title="Held frames: raw sum and fixed training-normalized sum")
    axes[1].set(xlabel="Seconds from visit 259 start", ylabel="Tone circular agreement", ylim=(0, 1.03))
    axes[0].legend(loc="lower left", fontsize=8)
    fig.suptitle("Per-tone response audit · calibration from first 20 ms only")
    for extension in ("png", "svg"):
        fig.savefig(HERE / f"response-comparison.{extension}", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
