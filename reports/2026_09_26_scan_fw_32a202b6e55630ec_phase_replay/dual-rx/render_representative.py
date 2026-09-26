# ruff: noqa: E402,I001
"""Recompute deterministic best/median/worst evaluation traces for method 24."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import run_corrected_direct as R

HERE = Path(__file__).parent


def main() -> None:
    with (HERE / "method24-corrected-direct-iq.csv").open() as stream:
        eligible = [
            row
            for row in csv.DictReader(stream)
            if row["split"] == "evaluation" and row["status"] == "completed"
        ]
    eligible.sort(key=lambda row: (float(row["random_cfo_rate_r"]), int(row["visit_index"])))
    selected_rows = [eligible[0], eligible[len(eligible) // 2], eligible[-1]]
    labels = ("worst", "median", "best")
    selection = {
        row["visit_index"]: row
        for row in json.loads((R.REPORT / "selection.json").read_text())["visits"]
    }
    source = R.C.CachedReplayVisitSource(R.CACHE_INDEX, R.REPORT / "selection.json")
    pairs = R._candidate_pairs()
    starts = R._starts()
    traces = []
    for label, rank_row in zip(labels, selected_rows, strict=True):
        visit_index = int(rank_row["visit_index"])
        selected = selection[visit_index]
        visit = source.read_visit(visit_index)
        iq = np.column_stack((visit.complex64(0), visit.complex64(1)))
        first, second = pairs[visit_index]
        seed = float(second["tracking_absolute_baseband_cfo_hz"]) - float(
            first["tracking_absolute_baseband_cfo_hz"]
        )
        train, held = R._split(starts, f"20260926:{visit_index}:method24-corrected")
        _, _, fit = R._fit(
            iq, visit.valid_mask, selected["valid_start_counter"], starts, train, seed
        )
        frequency, rate = fit[1:]
        models = {}
        for name, model_frequency, model_rate in (
            ("raw", 0.0, 0.0),
            ("constant_cfo", frequency, 0.0),
            ("cfo_rate", frequency, rate),
        ):
            phasors, coherence, centers = R.HB.time_phasors(
                iq, R.RATE, model_frequency, model_rate, starts
            )
            models[name] = {
                "phase_rad": np.angle(phasors).tolist(),
                "coherence": coherence.tolist(),
                "center_seconds": centers.tolist(),
            }
        traces.append(
            {
                "selection_rule": label,
                "visit_index": visit_index,
                "random_held_r": float(rank_row["random_cfo_rate_r"]),
                "train_indices": train.tolist(),
                "held_indices": held.tolist(),
                "relative_cfo_hz": frequency,
                "relative_rate_hz_s": rate,
                "wrong_time_median_coherence": float(rank_row["wrong_time_median_coherence"]),
                "models": models,
            }
        )
    (HERE / "method24-representative-traces.json").write_text(json.dumps(traces) + "\n")
    figure, axes = plt.subplots(
        3, 1, figsize=(10, 8), sharex=True, sharey=True, constrained_layout=True
    )
    for axis, trace in zip(axes, traces, strict=True):
        for name, color in (("raw", "0.65"), ("constant_cfo", "#377eb8"), ("cfo_rate", "#e41a1c")):
            model = trace["models"][name]
            axis.plot(
                np.asarray(model["center_seconds"]) * 1_000,
                np.degrees(model["phase_rad"]),
                ".-",
                ms=3,
                lw=0.8,
                color=color,
                label=name.replace("_", " "),
            )
        axis.set_ylabel(f"{trace['selection_rule']} v{trace['visit_index']}\nphase (deg)")
        axis.set_ylim(-190, 190)
        axis.grid(alpha=0.2)
    axes[0].legend(ncol=3)
    axes[-1].set_xlabel("Local dwell time (ms); no nuisance phase intercept removed")
    figure.savefig(HERE / "method24-representative-traces.png", dpi=180, facecolor="white")


if __name__ == "__main__":
    main()
