"""Chart native preparation memory and independently scored paired positions."""

import argparse
import csv
import gzip
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import local_output
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .prep_stream_trial import METHODS, PLAN, REPORT

STAGES = {
    "graph": "Graph\ntracks",
    "regional_bank": "Regional\nbank",
    "initial_sky": "Initial\nsky",
    "phase_history": "Causal\nhistory",
    "phase_forecast": "Phase\nforecast",
    "native_to_prepared": "Prepared\ninput",
}
SERIES = (
    (-0.18, "control", "Aligned compact finish", "#476173"),
    (0.18, "stream", "Bounded sky preparation", "#287a62"),
)


def metrics(row):
    result = row["result"]
    m = result["metrics"]
    prep = m.get("prep_stream_measurement", {})
    stages = prep.get("stages", {})
    peak = m.get("early_memory", {}).get("independent_sample_max_kib", {})
    return dict(
        id=row["id"],
        method=row["method"],
        status=result["status"],
        cpu=row["cpu"],
        whole_wall_s=row["worker_wall_s"],
        whole_cpu_s=row["worker_cpu_s"],
        whole_peak_rss_kib=m.get("numerical_worker_peak_rss_kib"),
        sampled_anon_rss_kib=peak.get("RssAnon"),
        sampled_file_rss_kib=peak.get("RssFile"),
        sampled_shmem_rss_kib=peak.get("RssShmem"),
        **{
            f"{name}_{name_measure}": stage.get(key)
            for name in ("native_decode", *STAGES)
            for stage in (stages.get(name, {}),)
            for key, name_measure in (("cpu_s", "cpu_s"), ("wall_s", "wall_s"))
        },
        **{
            f"{name}_peak_kib": stages.get(name, {}).get("after", {}).get("peak_rss_kib")
            for name in ("native_decode", *STAGES)
        },
        retained_element_cache_bytes=stages.get("element_cache", {}).get("retained_bytes"),
        cache_hit_count=stages.get("element_cache", {}).get("hits"),
        max_coarse_output_bytes=prep.get("streamed", {}).get("max_coarse_output_bytes"),
        retained_state_bytes=prep.get("streamed", {}).get("retained_state_bytes"),
        candidate_count=prep.get("evidence", {}).get("regional_bank", {}).get("selected"),
    )


def data(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    result = []
    for method in METHODS:
        name = f"{method}-positions.jsonl.gz"
        archive = report / name
        if _sha(archive) != lock["files"][name]:
            raise ValueError("resource figure is not using sealed predictions")
        result.extend(
            metrics(p) for p in map(json.loads, gzip.decompress(archive.read_bytes()).splitlines())
        )
    return result


def preparation(report, rows):
    index = {(r["id"], r["method"]): r for r in rows}
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.2), sharey=True)
    x = np.arange(len(STAGES))
    for axis, case in zip(axes, PLAN, strict=True):
        axis.axhline(512, color="#99745f", linewidth=1, linestyle="--", label="512 MiB reference")
        for shift, role, label, color in SERIES:
            item = index[case, METHODS[role]]
            size = [item[k + "_peak_kib"] for k in STAGES]
            axis.bar(
                x + shift,
                [n / 1024 if n is not None else np.nan for n in size],
                width=0.35,
                color=color,
                zorder=3,
                label=label,
            )
        axis.set_xticks(x, list(STAGES.values()), fontsize=8)
        axis.set_title(case, fontsize=11)
        axis.grid(axis="y", alpha=0.25)
    peak = max(
        (r[k + "_peak_kib"] for r in rows for k in STAGES if r[k + "_peak_kib"] is not None),
        default=512 * 1024,
    )
    axes[0].set_ylim(0, 1.09 * max(512, peak / 1024))
    axes[0].set_ylabel("Cumulative process peak RSS (MiB)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center", ncol=3, frameon=False)
    fig.subplots_adjust(top=0.80, bottom=0.17, wspace=0.10)
    fig.savefig(report / "preparation-memory.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def positions(report):
    with (report / "scores.csv").open() as stream:
        rows = {(r["id"], r["method"], r["arm"]): r for r in csv.DictReader(stream)}
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4), sharey=True)
    for axis, arm, title in zip(axes, ("c0", "fitted_c"), ("c = 0", "Fitted c"), strict=True):
        for shift, role, label, color in SERIES:
            values = [rows[c, METHODS[role], arm]["error_km"] for c in PLAN]
            axis.scatter(
                np.arange(len(PLAN)) + shift,
                [float(x) if x else np.nan for x in values],
                color=color,
                s=65,
                label=label,
                zorder=3,
            )
        axis.set_xticks(range(len(PLAN)), list(PLAN), fontsize=9)
        axis.set_title(title, fontsize=11)
        axis.set_xlim(-0.53, len(PLAN) - 0.47)
        axis.grid(axis="y", alpha=0.25)
    peak = max((float(r["error_km"]) for r in rows.values() if r["error_km"]), default=1)
    axes[0].set_ylim(0, 1.12 * max(peak, 1e-6))
    axes[0].set_ylabel("Position error (km)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center", ncol=2, frameon=False)
    fig.subplots_adjust(top=0.76, bottom=0.16, wspace=0.11)
    fig.savefig(report / "positions.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=local_output, default=REPORT)
    report = p.parse_args().report
    rows = data(report)
    csv_file(report / "resources.csv", rows)
    preparation(report, rows)
    positions(report)


if __name__ == "__main__":
    main()
