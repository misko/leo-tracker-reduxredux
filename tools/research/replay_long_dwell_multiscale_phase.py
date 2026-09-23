"""Replay 105915 double-difference phase in independently bounded chunks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor
from leo.analysis.starlink.templates import (
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)
from leo.storage import RecordingStore

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "reports/2026_09_23_long_dwell_multiscale_protocol.md"
REFERENCE = ROOT / "reports/figures/2026_09_16_dual_rx_pilot_phase/105915-coherent-pilot-20ms.json"
OUTPUT = ROOT / "reports/figures/2026_09_23_long_dwell_multiscale_phase"
SESSION = "cap-20260825T105915-2770b84587cc"
FS = 2_500_000
CENTERS = (24.0, 25.5, 27.0, 28.5, 30.0)
DURATIONS_MS = (600, 300, 150, 120, 60, 20)
SEED = 20260923
EPOCHS = {"A": 67_500_908, "B": 67_501_006}
MODELS = {
    "A": (
        (25.800, -3514.6676537163635, 372727.86206062447),
        (23.650, -3522.9132283698773, -180335.85438927953),
    ),
    "B": (
        (23.625, -3894.0112036045334, 490104.87639001757),
        (25.175, -3885.094498606725, -76458.44384059052),
    ),
}


def wrap(value):
    return np.angle(np.exp(1j * np.asarray(value)))


def carrier_phase(model, time_s):
    reference, slope, frequency = model
    delta = np.asarray(time_s) - reference
    return 2 * np.pi * (0.5 * slope * delta**2 + frequency * delta)


def frame_starts(epoch, left, right):
    low = int(np.floor((left - epoch) / (FS / 750))) - 2
    high = int(np.ceil((right - epoch) / (FS / 750))) + 2
    length = round(FS / 750)
    return np.asarray(
        [
            epoch + round(k * FS / 750)
            for k in range(low, high + 1)
            if left <= epoch + round(k * FS / 750) and epoch + round(k * FS / 750) + length <= right
        ],
        dtype=int,
    )


def split_frames(count, salt):
    order = np.random.default_rng(SEED + salt).permutation(count)
    train = np.zeros(count, dtype=bool)
    train[order[: count // 2]] = True
    return train


def correlations(iq, read_start, starts, shift, model, receiver, template):
    symbol_end = round(66 * FS * OFDM_SYMBOL_DURATION_S)
    symbol_begin = round(2 * FS * OFDM_SYMBOL_DURATION_S)
    offsets = np.arange(symbol_begin, symbol_end)
    output = []
    for start in starts + shift:
        absolute = start + offsets
        local = absolute - read_start
        phase = carrier_phase(model, absolute / FS)
        output.append(
            np.sum(iq[local, receiver] * np.exp(-1j * phase) * np.conj(template[offsets]))
        )
    return np.asarray(output)


def source_phase(iq, read_start, center_s, duration_ms, source, frozen_shift, local_timing):
    half = round(duration_ms * FS / 2000)
    center = round(center_s * FS)
    starts = frame_starts(EPOCHS[source], center - half, center + half)
    if len(starts) < 6:
        return None
    train = split_frames(len(starts), int(center_s * 100) + duration_ms + ord(source))
    exact = qin_edge_pilot_frame(FS, "upper")
    control = qin_edge_pilot_frame(FS, "upper", symbol_roll=17)
    shifts = range(-80, 81) if local_timing else (frozen_shift,)
    scores = []
    for shift in shifts:
        c = correlations(iq, read_start, starts, shift, MODELS[source][0], 0, exact)
        scores.append(float(np.sum(abs(c[train]) ** 2)))
    shift = list(shifts)[int(np.argmax(scores))]
    coeff = []
    controls = []
    for receiver in (0, 1):
        coeff.append(
            correlations(iq, read_start, starts, shift, MODELS[source][receiver], receiver, exact)
        )
        controls.append(
            correlations(iq, read_start, starts, shift, MODELS[source][receiver], receiver, control)
        )
    product = coeff[1] * np.conj(coeff[0])
    weights = np.sqrt(abs(coeff[0]) * abs(coeff[1]))
    actual_starts = starts + shift
    frequency, phase, resultant = fit_linear_phasor(
        product[train], actual_starts[train] / FS, weights[train], center_s
    )
    predicted = np.exp(
        1j * (phase + 2 * np.pi * frequency * (actual_starts[~train] / FS - center_s))
    )
    held_unit = product[~train] / np.maximum(abs(product[~train]), 1e-30)
    held_resultant = float(abs(np.average(held_unit * np.conj(predicted), weights=weights[~train])))
    restored = wrap(
        phase
        + carrier_phase(MODELS[source][1], center_s)
        - carrier_phase(MODELS[source][0], center_s)
    )
    exact_power = sum(float(np.sum(abs(c[~train]) ** 2)) for c in coeff)
    control_power = sum(float(np.sum(abs(c[~train]) ** 2)) for c in controls)
    wrong = [
        correlations(iq, read_start, starts, shift + 37, MODELS[source][receiver], receiver, exact)
        for receiver in (0, 1)
    ]
    wrong_power = sum(float(np.sum(abs(c[~train]) ** 2)) for c in wrong)
    return {
        "phase_pre_restore_rad": float(phase),
        "phase_restored_rad": float(restored),
        "timing_shift_samples": shift,
        "train_frames": int(np.sum(train)),
        "held_frames": int(np.sum(~train)),
        "train_resultant": resultant,
        "held_resultant": held_resultant,
        "held_exact_control_power_ratio": exact_power / max(control_power, 1e-30),
        "held_exact_wrong_timing_power_ratio": exact_power / max(wrong_power, 1e-30),
        "residual_product_hz": frequency,
    }


def main():
    reference = json.loads(REFERENCE.read_text())
    reference_rows = reference["windows"]
    output = {
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reference_sha256": hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
        "rows": [],
    }
    store = RecordingStore.open_read_only(Path("/srv/bulk/leo"))
    try:
        bundle = store.inspect(SESSION)
        output["manifest_sha256"] = bundle.manifest_sha256
        for center_s in CENTERS:
            nearest = min(reference_rows, key=lambda row: abs(row["center_s"] - center_s))
            frozen_shifts = {
                track["track"]: track["timing_shift_samples"] for track in nearest["tracks"]
            }
            ref_phase = (
                np.radians(nearest["differential_phase_deg"]) if nearest["both_qualified"] else None
            )
            read_start = round((center_s - 0.301) * FS)
            raw = store.read_ci16(
                bundle, "stream-0", read_start, round(0.602 * FS), receiver_ids=(0, 1), verify=True
            )
            iq = raw[..., 0].astype(float) + 1j * raw[..., 1].astype(float)
            for duration_ms in DURATIONS_MS:
                for mode, local in (("frozen_timing", False), ("local_timing", True)):
                    sources = {
                        source: source_phase(
                            iq,
                            read_start,
                            center_s,
                            duration_ms,
                            source,
                            frozen_shifts[source],
                            local,
                        )
                        for source in ("A", "B")
                    }
                    phase = (
                        None
                        if any(value is None for value in sources.values())
                        else float(
                            wrap(
                                sources["A"]["phase_restored_rad"]
                                - sources["B"]["phase_restored_rad"]
                            )
                        )
                    )
                    pre_restore = (
                        None
                        if any(value is None for value in sources.values())
                        else float(
                            wrap(
                                sources["A"]["phase_pre_restore_rad"]
                                - sources["B"]["phase_pre_restore_rad"]
                            )
                        )
                    )
                    output["rows"].append(
                        {
                            "center_s": center_s,
                            "duration_ms": duration_ms,
                            "mode": mode,
                            "reference_phase_rad": ref_phase,
                            "double_difference_pre_restore_rad": pre_restore,
                            "double_difference_rad": phase,
                            "circular_error_rad": None
                            if phase is None or ref_phase is None
                            else float(wrap(phase - ref_phase)),
                            "sources": sources,
                        }
                    )
    finally:
        store.close()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "results.json").write_text(json.dumps(output, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for mode, marker in (("frozen_timing", "o"), ("local_timing", "s")):
        for duration in DURATIONS_MS:
            rows = [
                row
                for row in output["rows"]
                if row["mode"] == mode
                and row["duration_ms"] == duration
                and row["double_difference_rad"] is not None
            ]
            axes[0].plot(
                [row["center_s"] for row in rows],
                [np.degrees(row["double_difference_rad"]) for row in rows],
                marker=marker,
                alpha=0.65,
                label=f"{mode} {duration}ms",
            )
            errors = [
                abs(np.degrees(row["circular_error_rad"]))
                for row in rows
                if row["circular_error_rad"] is not None
            ]
            axes[1].scatter(duration, np.median(errors) if errors else np.nan, marker=marker)
    axes[0].set(xlabel="Capture time (s)", ylabel="Restored DD phase (deg)")
    axes[1].set(
        xscale="log",
        xlabel="Independent chunk duration (ms)",
        ylabel="Median circular error vs retained 20ms curve (deg)",
    )
    axes[0].legend(fontsize=6, ncol=2)
    for axis in axes:
        axis.grid(alpha=0.2)
    fig.savefig(OUTPUT / "phase-recovery-by-duration.png", dpi=160)


if __name__ == "__main__":
    main()
