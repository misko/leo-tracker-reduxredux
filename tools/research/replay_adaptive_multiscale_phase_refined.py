"""Apply the independent-chunk phase frontend to five adaptive visits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import (
    coherent_pilot_frames,
    fit_linear_phasor,
    pilot_symbol_reference_offsets_s,
)
from leo.analysis.starlink.fractional_epoch import fractional_take, fractional_take_bounds
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, qin_edge_pilot_frame
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tools.research import replay_long_dwell_multiscale_phase as frontend

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "reports/figures/2026_09_23_adaptive_multiscale_phase_refined"
BINDING = DIRECTORY / "binding.json"
PROTOCOL = ROOT / "reports/2026_09_23_adaptive_multiscale_phase_refined_protocol.md"
DURATIONS = (120, 60, 20)


def frame_origin_times(starts, shift, fraction, sample_rate_hz):
    """Times of phasors already transported to each coherent frame origin."""
    return (np.asarray(starts) + shift + fraction) / sample_rate_hz


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


def symbol_correlations(iq, starts, shift, model, receiver, template, fraction):
    """Correlate every frame and pilot symbol with one fractional IQ take.

    This is algebraically the former frame/symbol loop: offsets are merely
    concatenated and reduced back into their original 64 symbol sums.  Keeping
    the fractional sampler call vectorized avoids repeating its 16-tap
    interpolation setup for every individual OFDM symbol.
    """
    symbols = np.arange(2, 66)
    begins = np.rint(symbols * frontend.FS * OFDM_SYMBOL_DURATION_S).astype(int)
    ends = np.rint((symbols + 1) * frontend.FS * OFDM_SYMBOL_DURATION_S).astype(int)
    offsets = np.concatenate(
        [np.arange(begin, end) for begin, end in zip(begins, ends, strict=True)]
    )
    boundaries = np.cumsum(ends - begins)[:-1]
    positions = np.asarray(starts, dtype=float)[:, None] + shift + offsets[None, :] + fraction
    left_guard, right_guard = fractional_take_bounds(fraction)
    if positions.min() < left_guard or positions.max() >= len(iq) - right_guard:
        raise ValueError("fractional correlation escapes bounded visit")
    received = fractional_take(iq[:, receiver], positions)
    phase = frontend.carrier_phase(model, positions / frontend.FS)
    terms = received * np.exp(-1j * phase) * np.conj(template[offsets])[None, :]
    return np.add.reduceat(terms, np.r_[0, boundaries], axis=1)


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
    symbols = np.arange(2, 66)
    offsets_s = pilot_symbol_reference_offsets_s(
        frontend.FS, OFDM_SYMBOL_DURATION_S, symbols, exact
    )
    fraction = source["fractional_epoch"]
    shifts = tuple(range(-80, 81)) if local_timing else (0,)
    scores = []
    for shift in shifts:
        ex = symbol_correlations(
            iq, starts[train], shift, frontend.MODELS[source_name][0], 0, exact, fraction
        )
        co = symbol_correlations(
            iq, starts[train], shift, frontend.MODELS[source_name][0], 0, control, fraction
        )
        frames, _, _, _ = coherent_pilot_frames(
            ex, co, offsets_s, OFDM_SYMBOL_DURATION_S
        )
        scores.append(float(np.sum(abs(frames) ** 2)))
    shift = shifts[int(np.argmax(scores))]
    coeff, controls, within_hz = [], [], []
    for receiver in (0, 1):
        ex = symbol_correlations(
            iq, starts, shift, frontend.MODELS[source_name][receiver], receiver, exact, fraction
        )
        co = symbol_correlations(
            iq, starts, shift, frontend.MODELS[source_name][receiver], receiver, control, fraction
        )
        _, _, residual, _ = coherent_pilot_frames(
            ex[train], co[train], offsets_s, OFDM_SYMBOL_DURATION_S
        )
        frames, control_frames, _, _ = coherent_pilot_frames(
            ex, co, offsets_s, OFDM_SYMBOL_DURATION_S, forced_residual_hz=residual
        )
        coeff.append(frames)
        controls.append(control_frames)
        within_hz.append(float(residual))
    product = coeff[1] * np.conj(coeff[0])
    weights = np.sqrt(abs(coeff[0]) * abs(coeff[1]))
    times = frame_origin_times(starts, shift, fraction, frontend.FS)
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
    wrong = []
    for r in (0, 1):
        ex = symbol_correlations(
            iq, starts, shift + 37, frontend.MODELS[source_name][r], r, exact, fraction
        )
        co = symbol_correlations(
            iq, starts, shift + 37, frontend.MODELS[source_name][r], r, control, fraction
        )
        frames, _, _, _ = coherent_pilot_frames(
            ex, co, offsets_s, OFDM_SYMBOL_DURATION_S, forced_residual_hz=within_hz[r]
        )
        wrong.append(frames)
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
        "train_only_within_frame_residual_hz": within_hz,
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
