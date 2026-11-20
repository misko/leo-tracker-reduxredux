"""Render detector work and actual packet latency from sealed paced outputs."""

import argparse
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import adaptive_arrival as trial
from . import arrival_queue as pace
from .arrival_queue_results import observed
from .full_v5_check import _sha
from .prefix_figures import csv_file

MODES = ("stock", "adaptive", "fifth")
LABELS = ("Four regions", "Queue-dependent", "Five regions")
COLORS = ("#333d64", "#087f70", "#a05c19")


def summarize(report):
    source_path = report / "source-lock.json"
    source = whole_iq.read(source_path)
    records, files = [], [source_path.name]
    for ident in trial.CPUS:
        spec = source["cases"][ident]
        reference = spec["modes"]["stock"]
        events = pace.readgz(whole_iq.checked(report / reference["events"], reference["sha256"]))
        files.append(reference["events"])
        for mode in MODES:
            prefix = f"{ident}-{mode}"
            receipt = report / f"{prefix}-lock.json"
            lock = whole_iq.read(receipt)
            if (lock["id"], lock["mode"], lock["source_lock_sha256"]) != (
                ident,
                mode,
                _sha(source_path),
            ):
                raise ValueError("raw result does not match the frozen receiver")
            for filename, digest in lock["files"].items():
                whole_iq.checked(report / filename, digest)
            rows = pace.readgz(report / f"{prefix}-trace.json.gz")
            service = whole_iq.read(report / f"{prefix}-service.json")["worker"]
            complete = lock["status"] == "complete"
            if complete and (not lock["raw_verified"] or len(rows) != len(events)):
                raise ValueError("a complete stream requires all source opportunities")
            for row in rows:
                trial.validate_event(row, events[row["visit"]], mode)
            counts = Counter(r["policy"] for r in rows if r["outcome"] == "emitted")
            summary = observed(rows, service, ident, mode, complete, events)
            records.append(
                dict(summary, stock_visits=counts["stock"], fifth_visits=counts["fifth"])
            )
            files.extend([receipt.name, *lock["files"]])
    return records, files


def plot(records, report):
    import matplotlib.pyplot as plt

    by_case = {(r["id"], r["mode"]): r for r in records}
    fig, axes = plt.subplots(1, 3, figsize=(13.1, 4.2), layout="constrained")
    ids = list(trial.CPUS)
    fig.suptitle("Real-time pilot search at the recorded delivery rate", fontsize=16, weight="bold")
    for ax, field, title in zip(
        axes,
        ("queue_drops", "age_p95_ms", "detector_cpu_s"),
        ("Valid radio visits dropped", "95th-percentile packet age (ms)", "Detector CPU (s)"),
        strict=True,
    ):
        for j, (mode, color, label) in enumerate(zip(MODES, COLORS, LABELS, strict=True)):
            points = [by_case[i, mode] for i in ids]
            for i, row in enumerate(points):
                offset = i + (j - 1) * 0.25
                if row["status"] != "complete":
                    ax.annotate("partial", (offset, 0), rotation=90)
                    continue
                val = row[field]
                ax.bar(offset, val, width=0.21, color=color, label=label if i == 0 else None)
                ax.annotate(
                    f"{val:.0f}",
                    (offset, val),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
        ax.set_xticks(range(len(ids)), ids)
        ax.set_title(title, fontsize=11)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.22)
        ax.set_axisbelow(True)
        ax.margins(y=0.15)
    fig.legend(
        *axes[0].get_legend_handles_labels(), loc="outside lower center", ncol=3, frameon=False
    )
    fig.savefig(report / "timing.png", dpi=180)
    fig.savefig(report / "timing.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def render(report):
    rows, files = summarize(report)
    csv_file(report / "timing.csv", rows)
    plot(rows, report)
    files.extend(["timing.csv", "timing.png", "timing.pdf"])
    seal = "stage-lock.json"
    complete = sum(row["status"] == "complete" for row in rows)
    save_json(
        report / seal,
        dict(
            cases=list(trial.CPUS),
            files={f: _sha(report / f) for f in files},
            renderer_sha256=_sha(Path(__file__)),
        ),
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="adaptive-arrival-native",
            title="Choosing the extra timing search at admission",
            image="timing.png",
            pdf="timing.pdf",
            csv="timing.csv",
            seal=seal,
            sample=f"DS26-0197 and DS29-0316 · {complete}/6 complete paced runs",
            boundary="Recorded delivery time to verified detector packet",
            note="One host core and one waiting slot. Position estimation has its own clock.",
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out", type=local_output, default=trial.REPORT)
    render(cli.parse_args().out)
