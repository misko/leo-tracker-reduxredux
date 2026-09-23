"""Apply the independent-chunk phase frontend to five adaptive visits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor
from leo.analysis.starlink.fractional_epoch import fractional_take
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, qin_edge_pilot_frame
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tools.research import replay_long_dwell_multiscale_phase as frontend

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_adaptive_multiscale_phase"
BINDING = DIRECTORY / "binding.json"
PROTOCOL = ROOT / "reports/2026_09_23_adaptive_multiscale_phase_protocol.md"
DURATIONS = (120, 60, 20)


def configure_frontend(row):
    frontend.FS = row["sample_rate_hz"]
    frontend.EPOCHS = {
        name: source["epoch"] for name, source in zip(("A", "B"), row["sources"], strict=True)
    }
    frontend.MODELS = {
        name: (
            (
                (source["epoch"] + source["fractional_epoch"]) / frontend.FS,
                0.0,
                source["rx0_acquired_cfo_hz"],
            ),
            (
                (source["epoch"] + source["fractional_epoch"]) / frontend.FS,
                0.0,
                source["rx1_applied_acquired_cfo_hz"],
            ),
        )
        for name, source in zip(("A", "B"), row["sources"], strict=True)
    }


def correlations(iq, starts, shift, model, receiver, template, fraction):
    begin = round(2 * frontend.FS * OFDM_SYMBOL_DURATION_S)
    end = round(66 * frontend.FS * OFDM_SYMBOL_DURATION_S)
    offsets = np.arange(begin, end)
    out = []
    for start in starts + shift:
        positions = start + offsets + fraction
        if positions.min() < 1 or positions.max() >= len(iq) - 2:
            raise ValueError("fractional correlation escapes bounded visit")
        received = fractional_take(iq[:, receiver], positions)
        phase = frontend.carrier_phase(model, positions / frontend.FS)
        out.append(np.sum(received * np.exp(-1j * phase) * np.conj(template[offsets])))
    return np.asarray(out)


def source_phase(iq, duration_ms, source_name, source, edge, local_timing):
    center_s = 0.06
    half = round(duration_ms * frontend.FS / 2000)
    center = round(center_s * frontend.FS)
    starts = frontend.frame_starts(frontend.EPOCHS[source_name], center - half, center + half)
    if len(starts) < 6:
        return None
    train = frontend.split_frames(len(starts), int(center_s * 100) + duration_ms)
    exact = qin_edge_pilot_frame(frontend.FS, edge)
    control = qin_edge_pilot_frame(frontend.FS, edge, symbol_roll=17)
    fraction = source["fractional_epoch"]
    shifts = tuple(range(-80, 81)) if local_timing else (0,)
    scores = []
    for shift in shifts:
        c = correlations(iq, starts, shift, frontend.MODELS[source_name][0], 0, exact, fraction)
        scores.append(float(np.sum(abs(c[train]) ** 2)))
    shift = shifts[int(np.argmax(scores))]
    coeff, controls = [], []
    for receiver in (0, 1):
        coeff.append(
            correlations(
                iq, starts, shift, frontend.MODELS[source_name][receiver], receiver, exact, fraction
            )
        )
        controls.append(
            correlations(
                iq,
                starts,
                shift,
                frontend.MODELS[source_name][receiver],
                receiver,
                control,
                fraction,
            )
        )
    product = coeff[1] * np.conj(coeff[0])
    weights = np.sqrt(abs(coeff[0]) * abs(coeff[1]))
    symbol_reference = np.mean(
        np.arange(
            round(2 * frontend.FS * OFDM_SYMBOL_DURATION_S),
            round(66 * frontend.FS * OFDM_SYMBOL_DURATION_S),
        )
    )
    times = (starts + shift + symbol_reference + fraction) / frontend.FS
    frequency, phase, resultant = fit_linear_phasor(
        product[train], times[train], weights[train], center_s
    )
    held_unit = product[~train] / np.maximum(abs(product[~train]), 1e-30)
    held_phase = float(
        np.angle(
            np.average(
                held_unit * np.exp(-2j * np.pi * frequency * (times[~train] - center_s)),
                weights=weights[~train],
            )
        )
    )
    predicted = np.exp(1j * (phase + 2 * np.pi * frequency * (times[~train] - center_s)))
    held_resultant = float(abs(np.average(held_unit * np.conj(predicted), weights=weights[~train])))
    restore = frontend.carrier_phase(
        frontend.MODELS[source_name][1], center_s
    ) - frontend.carrier_phase(frontend.MODELS[source_name][0], center_s)
    exact_power = sum(float(np.sum(abs(c[~train]) ** 2)) for c in coeff)
    control_power = sum(float(np.sum(abs(c[~train]) ** 2)) for c in controls)
    wrong = [
        correlations(iq, starts, shift + 37, frontend.MODELS[source_name][r], r, exact, fraction)
        for r in (0, 1)
    ]
    wrong_power = sum(float(np.sum(abs(c[~train]) ** 2)) for c in wrong)
    return {
        "train_phase_restored_rad": float(frontend.wrap(phase + restore)),
        "held_phase_restored_rad": float(frontend.wrap(held_phase + restore)),
        "timing_shift_samples": shift,
        "train_frames": int(train.sum()),
        "held_frames": int((~train).sum()),
        "train_resultant": resultant,
        "held_resultant": held_resultant,
        "held_exact_control_power_ratio": exact_power / max(control_power, 1e-30),
        "held_exact_wrong_timing_power_ratio": exact_power / max(wrong_power, 1e-30),
        "residual_product_hz": frequency,
    }


def main():
    binding = json.loads(BINDING.read_text())
    output = {
        "binding_sha256": hashlib.sha256(BINDING.read_bytes()).hexdigest(),
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "rows": [],
    }
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        with AdaptiveHopAnalysisInputStore(store).source(binding["session_id"]) as source:
            if source.input_manifest_sha256 != binding["input_manifest_sha256"]:
                raise ValueError("adaptive source manifest changed")
            for bound in binding["rows"]:
                event = source.visits[bound["iq_ordinal"]].event
                if event.visit_index != bound["visit_index"]:
                    raise ValueError("IQ ordinal no longer identifies visit")
                iq = source.read_visit(bound["iq_ordinal"])
                configure_frontend(bound)
                for duration in DURATIONS:
                    for mode, local in (("frozen_timing", False), ("local_timing", True)):
                        phases = {
                            name: source_phase(iq, duration, name, source_row, bound["edge"], local)
                            for name, source_row in zip(("A", "B"), bound["sources"], strict=True)
                        }
                        failed = any(value is None for value in phases.values())
                        held = (
                            None
                            if failed
                            else float(
                                frontend.wrap(
                                    phases["B"]["held_phase_restored_rad"]
                                    - phases["A"]["held_phase_restored_rad"]
                                )
                            )
                        )
                        train = (
                            None
                            if failed
                            else float(
                                frontend.wrap(
                                    phases["B"]["train_phase_restored_rad"]
                                    - phases["A"]["train_phase_restored_rad"]
                                )
                            )
                        )
                        output["rows"].append(
                            {
                                "visit_index": bound["visit_index"],
                                "duration_ms": duration,
                                "mode": mode,
                                "held_double_difference_rad": held,
                                "train_double_difference_rad": train,
                                "sources": phases,
                                "failure": None if not failed else "insufficient_frames",
                            }
                        )
    finally:
        store.close()
    reference = {
        (r["visit_index"], r["mode"]): r["held_double_difference_rad"]
        for r in output["rows"]
        if r["duration_ms"] == 120
    }
    for row in output["rows"]:
        ref = reference[(row["visit_index"], row["mode"])]
        row["circular_difference_from_120ms_rad"] = (
            None
            if ref is None or row["held_double_difference_rad"] is None
            else float(frontend.wrap(row["held_double_difference_rad"] - ref))
        )
    (DIRECTORY / "results.json").write_text(json.dumps(output, indent=2) + "\n")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), sharey=True, layout="constrained")
    for ax, duration in zip(axes, DURATIONS, strict=True):
        for mode, marker in (("frozen_timing", "o"), ("local_timing", "s")):
            rows = [
                r
                for r in output["rows"]
                if r["duration_ms"] == duration
                and r["mode"] == mode
                and r["held_double_difference_rad"] is not None
            ]
            ax.scatter(
                [r["visit_index"] for r in rows],
                np.degrees([r["held_double_difference_rad"] for r in rows]),
                marker=marker,
                label=mode.replace("_", " "),
            )
        ax.set(title=f"{duration} ms", xlabel="Visit index", ylim=(-180, 180))
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Held wrapped high−low DD phase (deg)")
    axes[0].legend(fontsize=8)
    fig.suptitle("Adaptive saved-IQ phase by independent within-visit duration")
    fig.savefig(DIRECTORY / "phase-by-duration.png", dpi=160)


if __name__ == "__main__":
    main()
