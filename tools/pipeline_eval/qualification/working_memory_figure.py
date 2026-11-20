"""Plot resource measurements from the sealed working-memory solver pairs."""

import argparse
import gzip
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import local_output, save_json
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .working_memory_trial import METHODS, PLAN, REPORT


def selected_rows(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    if lock["cases"] != list(PLAN) or lock["source_lock_sha256"] != _sha(
        report / "source-lock.json"
    ):
        raise ValueError("figure roster or source lock differs")
    files = {mode: f"{mode}-positions.jsonl.gz" for mode in METHODS}
    if any(_sha(report / name) != lock["files"][name] for name in files.values()):
        raise ValueError("prediction archive differs from its locked bytes")
    bundles = {}
    for mode, name in files.items():
        records = list(map(json.loads, gzip.decompress((report / name).read_bytes()).splitlines()))
        if [r["case_key"] for r in records] != list(PLAN):
            raise ValueError("position rows differ from locked roster")
        bundles[mode] = {r["case_key"]: r for r in records}
    for detector in ("ordinary", "capture-era"):
        cases = [r["id"] for r in bundles["stock"].values() if r["detector"] == detector]
        save_json(
            report / f"{detector}-figure-lock.json",
            dict(cases=cases, files={name: lock["files"][name] for name in files.values()}),
        )
    return bundles


def resources(row):
    if row["result"]["status"] != "ok":
        return None
    m = row["result"]["metrics"]
    early = m["working_memory"]
    measured = m["measured_stages"]
    returned = early["explorations"][0]["computed"][0]
    return dict(
        regional_bank_rss_kib=early["regional_bank"]["after"]["peak_rss_kib"],
        prepared_input_rss_kib=measured["native_plus_sky_history"]["self_peak_rss_kib"],
        initial_position_rss_kib=measured["initial_position"]["self_peak_rss_kib"],
        complete_worker_rss_kib=m["compact_worker"]["self_peak_rss_kib"],
        regional_bank_cpu_s=early["regional_bank"]["cpu_s"],
        initial_position_cpu_s=measured["initial_position"]["cpu_s"],
        initial_position_wall_s=measured["initial_position"]["wall_s"],
        worker_cpu_s=row["worker_cpu_s"],
        worker_wall_s=row["worker_wall_s"],
        association_calls=sum(len(e["computed"]) for e in early["explorations"]),
        reused_calls=early["reuse"].get("reused_associations", 0),
        returned_projection_and_diagnostic_bytes=returned["predicted_payload_bytes"]
        + returned["diagnostic_payload_bytes"],
    )


def run(report):
    bundles = selected_rows(report)
    records = []
    for mode, cases in bundles.items():
        for key, row in cases.items():
            stats = resources(row)
            records.append(
                dict(case_key=key, method=mode, status=row["result"]["status"], **(stats or {}))
            )
    ref = {(r["case_key"], r["method"]): r for r in records}
    csv_file(report / "resources.csv", records)
    fig, axes = plt.subplots(1, len(PLAN), sharey=True, figsize=(11, 4.4))
    stages = ("regional_bank", "prepared_input", "initial_position", "complete_worker")
    ticks = ("Regional\nbank", "Prepared\ninput", "Initial\nfit", "Complete\nworker")
    for axis, key in zip(axes, PLAN, strict=True):
        axis.axhline(512, color="#8d7062", linewidth=1.0, linestyle="--", label="512 MiB reference")
        for shift, mode, label, color in (
            (-0.18, "stock", "Compact secant", "#486173"),
            (0.18, "candidate", "One association", "#287a61"),
        ):
            item = ref[key, mode]
            if item["status"] == "ok":
                axis.bar(
                    np.arange(len(ticks)) + shift,
                    [item[stage + "_rss_kib"] / 1024 for stage in stages],
                    width=0.35,
                    label=label,
                    color=color,
                    zorder=3,
                )
        axis.set_xticks(range(len(ticks)), ticks, fontsize=9)
        axis.set_title(
            key.rsplit("-DS", 1)[0].replace("-", " ").capitalize()
            + "\nDS"
            + key.rsplit("-DS", 1)[1],
            fontsize=11,
        )
        axis.set_ylim(0, 1150)
        axis.set_yticks(range(0, 1101, 200))
        axis.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Cumulative process peak RSS (MiB)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=3, loc="upper center", frameon=False)
    fig.subplots_adjust(top=0.76, bottom=0.20, wspace=0.14)
    fig.savefig(report / "resources.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=local_output, default=REPORT)
    run(p.parse_args().report)


if __name__ == "__main__":
    main()
