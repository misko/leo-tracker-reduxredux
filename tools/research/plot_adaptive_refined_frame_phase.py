"""Visualize saved adaptive fits frame by frame, with no parameter refitting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import (
    coherent_pilot_frames,
    pilot_symbol_reference_offsets_s,
)
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, qin_edge_pilot_frame
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from tools.research import replay_adaptive_multiscale_phase_refined as replay


def main():
    directory = replay.DIRECTORY
    binding = json.loads(replay.BINDING.read_text())
    results_path = directory / "results.json"
    results = json.loads(results_path.read_text())
    if results["binding_sha256"] != hashlib.sha256(replay.BINDING.read_bytes()).hexdigest():
        raise ValueError("binding differs from fitted replay")
    fitted = {
        row["visit_index"]: row
        for row in results["rows"]
        if row["duration_ms"] == 120 and row["mode"] == "frozen_timing"
    }
    output = {
        "description": "Visualization only: saved 120 ms frozen-timing fits; no refitting",
        "results_sha256": hashlib.sha256(results_path.read_bytes()).hexdigest(),
        "rows": [],
    }
    fig, axes = plt.subplots(5, 2, figsize=(13, 13), sharex=True, sharey=True, layout="constrained")
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        with AdaptiveHopAnalysisInputStore(store).source(binding["session_id"]) as source:
            if source.input_manifest_sha256 != binding["input_manifest_sha256"]:
                raise ValueError("IQ manifest changed")
            for row_index, bound in enumerate(binding["rows"]):
                ordinal = bound["iq_ordinal"]
                if source.visits[ordinal].event.visit_index != bound["visit_index"]:
                    raise ValueError("visit binding changed")
                iq = source.read_visit(ordinal)
                replay.configure_frontend(bound)
                fs = bound["sample_rate_hz"]
                exact = qin_edge_pilot_frame(fs, bound["edge"])
                control = qin_edge_pilot_frame(fs, bound["edge"], symbol_roll=17)
                offsets = pilot_symbol_reference_offsets_s(
                    fs, OFDM_SYMBOL_DURATION_S, np.arange(2, 66), exact
                )
                for column, (name, src) in enumerate(
                    zip(("A", "B"), bound["sources"], strict=True)
                ):
                    fit = fitted[bound["visit_index"]]["sources"][name]
                    starts = replay.frontend.frame_starts(src["epoch"], 0, round(0.12 * fs))
                    train = replay.frontend.split_frames(len(starts), 126)
                    shift = fit["timing_shift_samples"]
                    fraction = src["fractional_epoch"]
                    coeff = []
                    for receiver in (0, 1):
                        model = replay.frontend.MODELS[name][receiver]
                        ex = replay.symbol_correlations(
                            iq, starts, shift, model, receiver, exact, fraction
                        )
                        co = replay.symbol_correlations(
                            iq, starts, shift, model, receiver, control, fraction
                        )
                        frames, _, _, _ = coherent_pilot_frames(
                            ex,
                            co,
                            offsets,
                            OFDM_SYMBOL_DURATION_S,
                            forced_residual_hz=fit["train_only_within_frame_residual_hz"][receiver],
                        )
                        coeff.append(frames)
                    times = replay.frame_origin_times(starts, shift, fraction, fs)
                    product = coeff[1] * np.conj(coeff[0])
                    restore = replay.frontend.carrier_phase(
                        replay.frontend.MODELS[name][1], 0.06
                    ) - replay.frontend.carrier_phase(replay.frontend.MODELS[name][0], 0.06)
                    phase = replay.frontend.wrap(
                        np.angle(product)
                        - 2 * np.pi * fit["residual_product_hz"] * (times - 0.06)
                        + restore
                    )
                    weights = np.sqrt(abs(coeff[0]) * abs(coeff[1]))
                    held_phase = np.angle(
                        np.average(np.exp(1j * phase[~train]), weights=weights[~train])
                    )
                    if (
                        abs(replay.frontend.wrap(held_phase - fit["held_phase_restored_rad"]))
                        > 1e-8
                    ):
                        raise ValueError("export disagrees with saved held phase")
                    output["rows"].append(
                        {
                            "visit_index": bound["visit_index"],
                            "source": name,
                            "time_s": times.tolist(),
                            "train": train.tolist(),
                            "phase_transported_to_center_rad": phase.tolist(),
                            "weights": weights.tolist(),
                        }
                    )
                    ax = axes[row_index, column]
                    ax.scatter(
                        times[train] * 1000,
                        np.degrees(phase[train]),
                        s=18,
                        facecolors="none",
                        edgecolors="0.5",
                        label="Train frames",
                    )
                    ax.scatter(
                        times[~train] * 1000,
                        np.degrees(phase[~train]),
                        s=17,
                        color="tab:blue",
                        label="Random held frames",
                    )
                    ax.axhline(
                        np.degrees(fit["train_phase_restored_rad"]),
                        color="0.35",
                        linestyle="--",
                        linewidth=1,
                        label="Train center phase",
                    )
                    ax.axhline(
                        np.degrees(fit["held_phase_restored_rad"]),
                        color="tab:blue",
                        linewidth=1,
                        label="Held center phase",
                    )
                    ax.set(
                        title=(
                            f"Visit {bound['visit_index']} · source {name} · "
                            f"held R={fit['held_resultant']:.2f}"
                        ),
                        ylim=(-180, 180),
                        xlim=(0, 120),
                        yticks=[-180, -90, 0, 90, 180],
                    )
                    ax.grid(alpha=0.2)
    finally:
        store.close()
    axes[0, 0].legend(fontsize=8, loc="lower left")
    for ax in axes[-1]:
        ax.set_xlabel("Time within dwell (ms)")
    for ax in axes[:, 0]:
        ax.set_ylabel("RX1−RX0 phase at dwell center (deg)")
    fig.suptitle(
        "Adaptive dwells: frame phase after saved train-only rate correction\n"
        "120 ms frozen timing · wrapped points · separate retunes · no refitting",
        fontsize=14,
    )
    fig.savefig(directory / "phase-within-dwells.png", dpi=160)
    (directory / "frame-phase.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
