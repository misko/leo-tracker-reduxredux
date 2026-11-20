"""Publish authenticated stage timings and numerical agreement for the two scout implementations."""

import argparse
import csv
import gzip
import json
from pathlib import Path

import matplotlib
import numpy as np

from ..__main__ import ROOT, save_json, write
from .differential_runtime_eval import REPORT, bindings
from .full_v5_check import _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

MODES = ("python", "fftw")
COHORTS = ("primary", "confirmation", "synthetic")
MEMBERS = (
    "plan.json",
    "paired.json.gz",
    "paired-runtime.json",
    "resource-python.json",
    "resource-fftw.json",
)


def times(rows, mode):
    keys = ("scout_cpu_ns", "native_cpu_ns", "scout_wall_ns", "native_wall_ns")
    return (
        np.array([[trial[k] for k in keys] for row in rows for trial in row["timing"][mode]]) / 1e6
    )


def summarize(rows):
    return dict(
        windows=len(rows),
        rank_one_lanes=sum(sum(r["top_ranks_match"]) for r in rows),
        complete_rank_lanes=sum(sum(r["full_ranks_match"]) for r in rows),
        canonical_native_payloads=sum(r["fftw_native_match"] for r in rows),
        selected_native_traces=sum(r["fftw_trace_match"] for r in rows),
        largest_lane_relative_linf=max(max(r["surf_relative_linf"]) for r in rows),
        time={
            mode: {
                "scout_cpu_median_ms": float(np.median(values[:, 0])),
                "native_cpu_median_ms": float(np.median(values[:, 1])),
                "combined_cpu_median_ms": float(np.median(values[:, :2].sum(axis=1))),
                "combined_wall_median_ms": float(np.median(values[:, 2:].sum(axis=1))),
                "combined_wall_p95_ms": float(np.quantile(values[:, 2:].sum(axis=1), 0.95)),
                "combined_wall_at_most_20ms": int(
                    np.count_nonzero(values[:, 2:].sum(axis=1) <= 20)
                ),
                "repeated_calls": len(values),
            }
            for mode in MODES
            for values in [times(rows, mode)]
        },
    )


def publish(work):
    plan = json.loads((work / "plan.json").read_bytes())
    if plan["sources"] != bindings():
        raise ValueError("stage source-lock verification failed")
    for bind in plan["libraries"].values():
        if _sha(Path(bind["path"])) != bind["sha256"]:
            raise ValueError("stage binary-lock verification failed")
    for name in MEMBERS:
        write(REPORT / name, (work / name).read_bytes())
    rows = json.loads(gzip.decompress((work / "paired.json.gz").read_bytes()))
    if [sum(row["cohort"] == c for row in rows) for c in COHORTS] != [24, 8, 14]:
        raise ValueError("unexpected paired roster")
    usable = [r for r in rows if "unavailable" not in r]
    summary = {
        cohort: summarize([r for r in usable if r["cohort"] == cohort]) for cohort in COHORTS
    }
    resources = {mode: json.loads((work / f"resource-{mode}.json").read_bytes()) for mode in MODES}
    save_json(
        REPORT / "summary.json",
        dict(
            cohorts=summary,
            resources={k: v["end"] for k, v in resources.items()},
            unavailable=len(rows) - len(usable),
        ),
    )
    keys = (
        "item",
        "cohort",
        "edge",
        "backend",
        "repeat",
        "scout_cpu_ms",
        "native_cpu_ms",
        "scout_wall_ms",
        "native_wall_ms",
        "native_payload_equal",
        "complete_ranks_equal",
    )
    with (REPORT / "stage.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(keys)
        for row in usable:
            for mode in MODES:
                for repeat, elapsed in enumerate(times([row], mode), start=1):
                    writer.writerow(
                        [
                            row["item"],
                            row["cohort"],
                            row["edge"],
                            mode,
                            repeat,
                            *elapsed,
                            row["fftw_native_match"],
                            all(row["full_ranks_match"]),
                        ]
                    )

    fig, (ax, total_ax) = plt.subplots(1, 2, layout="constrained", figsize=(9, 3.7))
    blocks = range(len(COHORTS))
    for mode, offset, label, color in (
        ("python", -0.18, "Frozen Python", "#546980"),
        ("fftw", 0.18, "FFTW", "#116d66"),
    ):
        x = [b + offset for b in blocks]
        group = [summary[c]["time"][mode] for c in COHORTS]
        ax.bar(x, [g["scout_cpu_median_ms"] for g in group], width=0.32, label=label, color=color)
        med = [g["combined_wall_median_ms"] for g in group]
        p95 = [g["combined_wall_p95_ms"] for g in group]
        total_ax.errorbar(
            x, med, yerr=[[0] * len(x), np.subtract(p95, med)], fmt="o", capsize=3, color=color
        )
    total_ax.axhline(20, linestyle="--", color="#a03632", linewidth=1.2, label="20 ms visit")
    for axis, title, ylabel in (
        (ax, "Scout only", "Median process CPU (ms)"),
        (total_ax, "Scout and native gate", "Median and p95 wall time (ms)"),
    ):
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.set_xticks(
            list(blocks), ["Primary\n24 saved", "Confirm.\n8 saved", "Synthetic\n14 controls"]
        )
        axis.set_ylim(bottom=0)
        axis.set_axisbelow(True)
        axis.grid(axis="y", color="#d7dfe2", linewidth=0.7)
        axis.legend(frameon=False)
    ax.set_ylim(0, 29)
    fig.suptitle("Differential scout runtime on identical dual-receiver windows")
    fig.savefig(REPORT / "stage.png", dpi=180)
    fig.savefig(REPORT / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="differential-runtime",
            title="Differential scout runtime parity",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="prediction-lock.json",
            boundary="Dual-RX CI16 to the hinted wide fractional detector on one host CPU",
            sample="24 primary and 8 confirmation saved visits plus 14 synthetic windows",
            note=(
                "FFTW reproduced every native payload in this cohort. "
                "Complete saved-IQ replay uses the frozen Python scout."
            ),
        ),
    )
    files = (
        *MEMBERS,
        "PROTOCOL.md",
        "README.md",
        "summary.json",
        "stage-figure.json",
        "stage.csv",
        "stage.png",
        "stage.pdf",
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=sorted({r["case"] for r in usable if "case" in r}),
            files={name: _sha(REPORT / name) for name in files},
            sources={
                **plan["sources"],
                str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__)),
                "tests/pipeline_eval/test_differential_runtime.py": _sha(
                    ROOT / "tests/pipeline_eval/test_differential_runtime.py"
                ),
            },
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    publish(parser.parse_args().work)
