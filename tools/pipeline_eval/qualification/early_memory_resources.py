"""Plot sealed early-stage and whole-worker resident memory."""

import argparse
import gzip
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import local_output
from .early_memory_trial import METHODS, PLAN, REPORT
from .full_v5_check import _sha
from .prefix_figures import csv_file

STAGES = {
    "prepare_native_scan": "Prepared\ninput",
    "ranked_initial": "Ranked\nsearch",
    "initial_selection": "Initial\nfit",
    "family_confidence": "Family\nconfidence",
    "complete_worker": "Complete\nworker",
}


def row(value):
    r = value["result"]
    m = r["metrics"].get("early_memory", {})
    complete = r["metrics"].get("stream_recovery_measurement", {})
    stage = {e["stage"]: e for e in complete.get("stages", [])} | m.get("stages", {})
    policy, sampled = m.get("policy", {}), m.get("independent_sample_max_kib", {})
    ranked = stage.get("ranked_initial", {})
    confidence = stage.get("family_confidence", {})
    return dict(
        id=value["id"],
        method=value["method"],
        status=r["status"],
        cpu=value["cpu"],
        wall_s=value["worker_wall_s"],
        cpu_s=value["worker_cpu_s"],
        **{
            k + "_peak_kib": stage.get(k, {}).get("after", {}).get("peak_rss_kib")
            for k in STAGES
            if k != "complete_worker"
        },
        complete_worker_peak_kib=m.get("whole_worker", {}).get("peak_rss_kib"),
        sampled_rss_anon_kib=sampled.get("RssAnon"),
        sampled_rss_file_kib=sampled.get("RssFile"),
        sampled_rss_shmem_kib=sampled.get("RssShmem"),
        rank_cpu_s=ranked.get("cpu_s"),
        confidence_cpu_s=confidence.get("cpu_s"),
        projector_total_calls=r["metrics"].get("compact_projections"),
        deferred_dense_grid_bytes=policy.get("max_deferred_grid_bytes"),
        track_grid_bytes=policy.get("max_track_grid_bytes"),
        track_projection_calls=policy.get("track_projections"),
        shared_field_queries=policy.get("shared_field_queries"),
    )


def run(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    data = []
    for method in METHODS:
        path = report / f"{method}-positions.jsonl.gz"
        if _sha(path) != lock["files"][path.name]:
            raise ValueError("resource inputs differ from their sealed records")
        data.extend(
            row(r) for r in map(json.loads, gzip.decompress(path.read_bytes()).splitlines())
        )
    csv_file(report / "resources.csv", data)
    cells = {(r["id"], r["method"]): r for r in data}
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.2), sharey=True)
    x = np.arange(len(STAGES))
    for axis, case in zip(axes, PLAN, strict=True):
        axis.axhline(512, color="#987560", linestyle="--", linewidth=1, label="512 MiB reference")
        for shift, method, label, color in (
            (-0.18, METHODS["control"], "Aligned compact finish", "#486173"),
            (0.18, METHODS["track"], "Track-column projection", "#267a60"),
        ):
            item = cells[case, method]
            values = [
                item[k + "_peak_kib"] / 1024 if item[k + "_peak_kib"] is not None else np.nan
                for k in STAGES
            ]
            axis.bar(x + shift, values, width=0.35, color=color, label=label, zorder=3)
        axis.set_xticks(x, list(STAGES.values()), fontsize=9)
        axis.set_title(case, fontsize=11)
        axis.set_ylim(bottom=0)
        axis.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Cumulative process peak RSS (MiB)")
    fig.legend(*axes[0].get_legend_handles_labels(), ncol=3, loc="upper center", frameon=False)
    fig.subplots_adjust(top=0.79, bottom=0.18, wspace=0.12)
    fig.savefig(report / "resources.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=local_output, default=REPORT)
    run(p.parse_args().report)


if __name__ == "__main__":
    main()
