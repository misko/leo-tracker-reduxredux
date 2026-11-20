"""Summarize cumulative RSS, useful resident buffers and recovery work."""

import argparse
import gzip
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import local_output
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .stream_recovery_trial import METHODS, PLAN, REPORT

STAGES = {
    "prepare_native_scan": "Prepared\ninput",
    "initial_selection": "Initial\nfit",
    "conservative_recovery": "Conservative\nrecovery",
    "history_policy": "Family\nhistory",
    "screen_candidates": "Residual\nscreen",
    "screen_reassociation_candidates": "Admission",
}


def resource_row(row):
    result = row["result"]
    stats = result["metrics"].get("stream_recovery_measurement", {})
    stage = {r["stage"]: r for r in stats.get("stages", [])}
    buffers = stats.get("candidate", {})
    big = stats.get("largest_conservative_profile") or {}
    return dict(
        id=row["id"],
        method=row["method"],
        status=result["status"],
        cpu=row["cpu"],
        complete_peak_rss_kib=stats.get("whole_worker", {}).get("peak_rss_kib"),
        worker_cpu_s=row["worker_cpu_s"],
        worker_wall_s=row["worker_wall_s"],
        **{
            name + "_peak_rss_kib": stage.get(name, {}).get("after", {}).get("peak_rss_kib")
            for name in STAGES
        },
        conservative_profile_prediction_bytes=big.get("prediction_bytes"),
        conservative_profile_returned_bytes=big.get("returned_bytes"),
        residual_bank_cpu_s=next(
            (r["cpu_s"] for r in stats.get("stages", []) if r["stage"] == "ecef_states"), None
        ),
        residual_cpu_s=stage.get("screen_candidates", {}).get("cpu_s"),
        admission_cpu_s=stage.get("screen_reassociation_candidates", {}).get("cpu_s"),
        projected_grids=buffers.get("projected_grids"),
        max_state_read_bytes=buffers.get("max_state_read_bytes"),
        max_output_grid_bytes=buffers.get("max_output_grid_bytes"),
        scratch_bytes=sum(r["scratch_bytes"] for k in ("ecef", "audit") for r in buffers.get(k, []))
        or None,
    )


def resources(report):
    seal = json.loads((report / "prediction-lock.json").read_bytes())
    rows = []
    for mode in METHODS:
        name = f"{mode}-positions.jsonl.gz"
        path = report / name
        if _sha(path) != seal["files"][name]:
            raise ValueError("resource plot source differs from its sealed prediction")
        rows.extend(
            resource_row(r)
            for r in map(json.loads, gzip.decompress(path.read_bytes()).splitlines())
        )
    csv_file(report / "resources.csv", rows)
    cells = {(r["id"], r["method"]): r for r in rows}
    fig, axes = plt.subplots(1, 2, sharey=True, figsize=(12.0, 4.3))
    labels = [*STAGES.values(), "Complete\nworker"]
    terms = [name + "_peak_rss_kib" for name in (*STAGES, "complete")]
    for axis, case in zip(axes, PLAN, strict=True):
        axis.axhline(512, color="#997660", linestyle="--", linewidth=1, label="512 MiB reference")
        for shift, method, label, color in (
            (-0.18, METHODS["control"], "Aligned compact finish", "#486173"),
            (0.18, METHODS["stream"], "Row-bounded recovery", "#287a61"),
        ):
            datum = cells[case, method]
            values = [datum[k] / 1024 if datum[k] is not None else np.nan for k in terms]
            axis.bar(
                np.arange(len(labels)) + shift,
                values,
                width=0.35,
                label=label,
                color=color,
                zorder=3,
            )
        axis.set_xticks(range(len(labels)), labels, fontsize=8)
        axis.set_title(case, fontsize=11)
        axis.grid(axis="y", alpha=0.25)
        axis.set_ylim(bottom=0.0)
    axes[0].set_ylabel("Cumulative process peak RSS (MiB)")
    fig.legend(*axes[0].get_legend_handles_labels(), ncol=3, loc="upper center", frameon=False)
    fig.subplots_adjust(top=0.78, bottom=0.19, wspace=0.12)
    fig.savefig(report / "resources.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=local_output, default=REPORT)
    resources(p.parse_args().report)


if __name__ == "__main__":
    main()
