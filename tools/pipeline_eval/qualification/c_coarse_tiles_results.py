"""Render and seal the complete standalone C coarse-kernel comparison."""

import argparse
import csv
import gzip
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from ..__main__ import local_output, save_json, write
from .c_coarse_tiles_trial import CASES, CPUS, METHODS, digest
from .capture_runtime import read

LABELS = {"incumbent": "Incumbent", "pairs": "Phase pairs", "tiles": "Symmetric carriers"}
COLORS = {"incumbent": "#334155", "pairs": "#0F766E", "tiles": "#B45309"}


def csv_file(path, rows):
    fields = list(dict.fromkeys(field for row in rows for field in row))
    with path.open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fields)
        writer.writeheader()
        writer.writerows(rows)


def archive_bytes(path, value):
    write(path, gzip.compress(value, mtime=0))


def profiles(results):
    accum = {}
    # Line profiling attributes inlined instructions to the originating kernel.
    pattern = re.compile(r"^\s*([\d.]+)\s+[\d.]+\s+([\d.]+)\s+(?:[\d.]+\s+)*([\w.]+)")
    for case in CASES:
        for method in METHODS:
            path = results / "profiles" / f"{case}-{method}.txt"
            stages = defaultdict(float)
            for line in path.read_text().splitlines():
                match = pattern.match(line)
                if not match:
                    continue
                _, seconds, function = match.groups()
                function = function.split(".", 1)[0]
                category = (
                    "anchor_fold"
                    if function in {"fold", "fold_tiles", "fold_block", "phase_pairs", "signed_sum"}
                    else "tone_rolling"
                    if function in {"roll", "sliding", "mix_tones", "demodulate"}
                    else "other"
                )
                stages[category] += float(seconds)
            total = sum(stages.values())
            if total <= 0 or not stages["anchor_fold"]:
                raise ValueError(f"profile attribution failed for {path}")
            accum[(case, method)] = [
                dict(
                    case=case,
                    method=method,
                    category=stage,
                    seconds=round(value, 4),
                    share=value / total,
                    total_profile_cpu_seconds=round(total, 4),
                )
                for stage, value in sorted(stages.items())
            ]
    return [row for values in accum.values() for row in values]


def distribution(values):
    a = np.asarray(values)
    return dict(
        count=len(a),
        min=float(a.min()),
        p50=float(np.median(a)),
        p95=float(np.percentile(a, 95)),
        max=float(a.max()),
    )


def timing_summary(timing, panel):
    held = {case: set(read(panel / case / "inputs.json")["held_visits"]) for case in CASES}
    keyed = defaultdict(dict)
    for row in timing:
        key = (row["case"], row["visit"], row["cpu"], row["replicate"])
        keyed[key][row["method"]] = row
    expected = len(CPUS) * 3 * 12
    if len(keyed) != expected or not all(set(rows) == set(METHODS) for rows in keyed.values()):
        raise ValueError("missing matched clock observations")
    metrics = ("detector_cpu_ns", "detector_wall_ns", "coarse_cpu_ns", "verify_cpu_ns")
    sample, aggregate = [], []
    for (case, visit, cpu, rep), rows in sorted(keyed.items()):
        base = rows["incumbent"]
        role = "held" if visit in held[case] else "blind"
        for method, row in rows.items():
            sample.append(
                dict(
                    case=case,
                    visit=visit,
                    cpu=cpu,
                    replicate=rep,
                    order=row["order"],
                    role=role,
                    method=method,
                    retries=row["retries"],
                    groups=row["groups"],
                    seeds=row["seeds"],
                    **{field.removesuffix("_ns") + "_ms": row[field] / 1e6 for field in metrics},
                    **{
                        field.removesuffix("_ns") + "_ratio": row[field] / base[field]
                        for field in metrics
                    },
                )
            )
    for subsets in ("all", "primary", "peer retry", "held", "blind"):
        for method in METHODS:
            rows = [
                row
                for row in sample
                if row["method"] == method
                and (
                    subsets == "all"
                    or row["role"] == subsets
                    or (subsets == "primary" and not row["retries"])
                    or (subsets == "peer retry" and row["retries"])
                )
            ]
            aggregate.append(
                dict(
                    subset=subsets,
                    method=method,
                    samples=len(rows),
                    **{
                        key: distribution([row[key] for row in rows])
                        for key in rows[0]
                        if key.endswith(("_ms", "_ratio"))
                    },
                )
            )
    return sample, aggregate


def stage_rows(samples, aggregate, grids, profile):
    rows = []
    visits = sorted({(r["case"], r["visit"], r["role"]) for r in samples})
    for method in METHODS[1:]:
        for case, visit, role in visits:
            values = [
                r["detector_cpu_ratio"]
                for r in samples
                if r["method"] == method and r["case"] == case and r["visit"] == visit
            ]
            rows.append(
                dict(
                    kind="paired_visit",
                    method=method,
                    case=case,
                    visit=visit,
                    role=role,
                    metric="detector_cpu_ratio",
                    value=median(values),
                    sample_count=len(values),
                )
            )
    for row in aggregate:
        if row["subset"] not in ("primary", "peer retry"):
            continue
        for key in ("coarse_cpu_ms", "verify_cpu_ms"):
            rows.append(
                dict(
                    kind="runtime",
                    method=row["method"],
                    group=row["subset"],
                    metric=key,
                    value=row[key]["p50"],
                    sample_count=row["samples"],
                )
            )
    for row in grids:
        rows.append(
            dict(
                kind="development_grid",
                method=row["method"],
                case=row["case"],
                visit=row["visit"],
                lane=row["lane"],
                group=row["anchors"],
                metric="max_abs_score",
                value=row["max_abs"],
                sample_count=row["cells"],
            )
        )
    for row in profile:
        if row["method"] == "incumbent":
            rows.append(
                dict(
                    kind="profile",
                    method=row["method"],
                    case=row["case"],
                    group=row["category"],
                    metric="sampled_cpu_share",
                    value=row["share"],
                    sample_count=round(100 * row["total_profile_cpu_seconds"]),
                )
            )
    rows.append(dict(kind="reference", metric="detector_cpu_ratio", value=1.0))
    return rows


def figure(report, rows):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axs = plt.subplots(2, 2, figsize=(11, 7.6), layout="constrained")
    fig.suptitle("Original dual-receiver detector on saved radio samples", fontweight="bold")
    ax = axs[0, 0]
    (equal,) = [r["value"] for r in rows if r["kind"] == "reference"]
    ax.axvline(equal, color="#64748B", linewidth=1)
    for rank, method in enumerate(METHODS[1:]):
        selected = [r for r in rows if r["kind"] == "paired_visit" and r["method"] == method]
        for j, row in enumerate(sorted(selected, key=lambda r: r["value"])):
            ax.scatter(
                row["value"],
                rank + (j - (len(selected) - 1) / 2) * 0.044,
                s=27,
                color=COLORS[method],
                marker="o" if row["role"] == "held" else "D",
            )
    ax.set_yticks(range(2), [LABELS[m] for m in METHODS[1:]])
    ax.set_xlabel("Median paired complete detector CPU ratio")
    ax.set_title("One point per held or blinded visit")
    ax.grid(axis="x", alpha=0.22)
    ax.legend(
        handles=[
            Line2D([], [], marker=marker, linestyle="none", color="#475569", label=label)
            for marker, label in (("o", "Historical held"), ("D", "Manifest hash holdout"))
        ],
        loc="upper left",
        frameon=False,
    )

    ax = axs[0, 1]
    colors = {"coarse_cpu_ms": "#1D4ED8", "verify_cpu_ms": "#94A3B8"}
    axes_labels = []
    for index, (group, method) in enumerate(
        (group, method) for group in ("primary", "peer retry") for method in METHODS
    ):
        axes_labels.append(f"{LABELS[method]} · {group}")
        start = 0
        for metric in ("coarse_cpu_ms", "verify_cpu_ms"):
            (row,) = [
                r
                for r in rows
                if r["kind"] == "runtime"
                and r["metric"] == metric
                and r["method"] == method
                and r["group"] == group
            ]
            ax.barh(
                index,
                row["value"],
                left=start,
                color=colors[metric],
                height=0.67,
                label=metric.removesuffix("_cpu_ms").capitalize() if index == 0 else None,
            )
            start += row["value"]
    ax.set_yticks(range(len(axes_labels)), axes_labels)
    ax.invert_yaxis()
    ax.set_xlabel("Stage median process CPU (ms)")
    ax.set_title("Primary and peer-retry visits")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.26), ncol=2, frameon=False)

    ax = axs[1, 0]
    for rank, method in enumerate(METHODS[1:]):
        selected = [r for r in rows if r["kind"] == "development_grid" and r["method"] == method]
        for j, row in enumerate(sorted(selected, key=lambda r: r["value"])):
            ax.scatter(
                row["value"],
                rank + (j - (len(selected) - 1) / 2) * 0.044,
                s=27,
                color=COLORS[method],
                marker="o" if row["group"] == 12 else "D",
            )
    ax.set_xscale("symlog", linthresh=1e-10)
    ax.set_yticks(range(2), [LABELS[m] for m in METHODS[1:]])
    ax.set_xlabel("Maximum absolute normalized score difference")
    ax.set_title("Full development grids by lane and mask")
    ax.grid(axis="x", alpha=0.22)
    ax.legend(
        handles=[
            Line2D([], [], marker=marker, linestyle="none", color="#475569", label=label)
            for marker, label in (("o", "12 anchors"), ("D", "22 anchors"))
        ],
        loc="upper left",
        frameon=False,
    )

    ax = axs[1, 1]
    for i, case in enumerate(CASES):
        left = 0
        for kind, color, label in (
            ("anchor_fold", "#1D4ED8", "Anchor fold"),
            ("tone_rolling", "#0F766E", "Tone rolling"),
            ("other", "#94A3B8", "Other"),
        ):
            (row,) = [
                r
                for r in rows
                if r["kind"] == "profile" and r["case"] == case and r["group"] == kind
            ]
            ax.barh(
                i,
                100 * row["value"],
                left=100 * left,
                height=0.64,
                color=color,
                label=label if i == 0 else None,
            )
            left += row["value"]
    ax.set_yticks(range(len(CASES)), CASES)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Sampled complete receiver CPU (%)")
    ax.set_title("Incumbent hot-path profile")
    ax.legend(loc="lower center", bbox_to_anchor=(0.54, -0.42), ncol=3, frameon=False)
    for extension in ("png", "pdf"):
        fig.savefig(report / f"stage.{extension}", dpi=170)
    plt.close(fig)


def resources(work, direct, builds):
    items = []
    for name in METHODS:
        target = work / "x86" / name
        su = next(
            p
            for p in target.glob("*.su")
            if p.name.endswith(("-portable_coarse.su", f"-c_coarse_tiles_{name}.su"))
        )
        stack = [
            {
                "function": row.split("\t")[0].split(":")[-1],
                "bytes": int(row.split("\t")[1]),
                "mode": row.split("\t")[2],
            }
            for row in su.read_text().splitlines()
        ]
        data = read(direct / f"{name}.json")
        items.append(
            dict(
                method=name,
                stack_records=stack,
                text_bytes=builds["builds"]["x86"][name]["sections"][".text"],
                executable_bytes=builds["builds"]["x86"][name]["file_bytes"],
                peak_rss_kib=data["peak_rss_kib"],
                workspace={
                    key: data[key]
                    for key in (
                        "coarse_workspace_bytes",
                        "verifier_workspace_bytes",
                        "input_bytes",
                    )
                },
            )
        )
    return items


def publish(work, panel, results, report, qualification=None):
    report.mkdir(parents=True, exist_ok=True)
    qualification = qualification or results
    timing = read(results / "timing.json")
    parity = read(results / "timed-parity.json")
    qual = read(qualification / "qualification.json")
    grids = read(qualification / "development.json")
    audit = read(qualification / "archive-audits.json")
    builds = read(work / "build-lock.json")
    samples, aggregate = timing_summary(timing, panel)
    prof = profiles(results)
    stage = stage_rows(samples, aggregate, grids, prof)
    csv_file(report / "stage.csv", stage)
    csv_file(report / "paired-clocks.csv", samples)
    csv_file(report / "qualification.csv", qual)
    csv_file(report / "development-grids.csv", grids)
    csv_file(report / "profile.csv", prof)
    for directory, names in (
        (results, ("timing.json", "timed-parity.json")),
        (qualification, ("candidates.json", "archive-audits.json")),
    ):
        for filename in names:
            archive_bytes(report / f"{filename}.gz", (directory / filename).read_bytes())
    for filename, source in (("input-lock.json", panel), ("build-lock.json", work)):
        write(report / filename, (source / filename).read_bytes())
    save_json(
        report / "input-cases.json", {case: read(panel / case / "inputs.json") for case in CASES}
    )
    save_json(
        report / "profiles.json",
        {path.name: path.read_text() for path in sorted((results / "profiles").glob("*.txt"))},
    )
    save_json(
        report / "summary.json",
        dict(
            timing=aggregate,
            resources=resources(work, results / "direct", builds),
            profile=prof,
            held_dev_gate_maxima={
                target: {
                    method: {
                        key: max(
                            a["verification"]["maximum_errors"][key]
                            for a in audit
                            if a["target"] == target and a["method"] == method
                        )
                        for key in audit[0]["verification"]["maximum_errors"]
                    }
                    for method in METHODS
                }
                for target in sorted({a["target"] for a in audit})
            },
            comparable_timed_pairs=len(parity),
            timed_pairs_with_discrete_changes=sum(
                not all(
                    row[key]
                    for key in (
                        "inventory_equal",
                        "ordered_peaks_equal",
                        "verifier_bytes_equal",
                    )
                )
                for row in parity
            ),
            qualification=qual,
            comparison_cpu=list(CPUS),
            measured_rounds=6,
            host={
                "cpu_model": next(
                    line.split(":", 1)[1].strip()
                    for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")
                ),
                "architecture": subprocess.check_output(["uname", "-m"], text=True).strip(),
            },
        ),
    )
    figure(report, stage)
    save_json(
        report / "direct-resources.json",
        {name: read(results / "direct" / f"{name}.json") for name in METHODS},
    )
    save_json(
        report / "stage-figure.json",
        {
            "version": 1,
            "id": "original-c-coarse-tiles",
            "title": "Shared Qin phase pairs and symmetric-carrier coarse acquisition",
            "boundary": "Resident stereo CI16 through regenerated coarse scores, original seed "
            "selection, fine acquisition, fractional GLRT and conditional peer retry",
            "sample": "Twelve authentic visits across three producers and six counterbalanced x86 "
            "rounds on CPUs 8 and 9",
            "note": "Position and physical embedded runtime were unmeasured.",
            "csv": "stage.csv",
            "image": "stage.png",
            "pdf": "stage.pdf",
            "seal": "qualification-lock.json",
        },
    )
    files = [
        path
        for path in sorted(report.iterdir())
        if path.is_file() and path.name != "qualification-lock.json"
    ]
    save_json(
        report / "qualification-lock.json",
        {
            "version": 1,
            "files": {path.name: digest(path) for path in files},
        },
    )


def publish_arm(results, report):
    """Seal numerical parity under emulation without mixing the timing samples."""
    audits = [row for row in read(results / "archive-audits.json") if row["target"] != "x86"]
    checks = [row for row in read(results / "qualification.json") if row["target"] != "x86"]
    if len(audits) != 2 * len(CASES) * len(METHODS) or len(checks) != 2 * 6 * len(METHODS):
        raise ValueError("both cross-target emulators require all six held visits")
    report.mkdir(parents=True, exist_ok=True)
    csv_file(report / "qualification.csv", checks)
    save_json(report / "archive-audits.json", audits)
    names = ("README.md", "qualification.csv", "archive-audits.json")
    save_json(
        report / "qualification-lock.json",
        {
            "version": 1,
            "boundary": "Cross-compiled detector numerical qualification under offline QEMU",
            "files": {name: digest(report / name) for name in names if (report / name).is_file()},
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("panel", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("report", type=local_output)
    parser.add_argument("--qualification", type=Path)
    args = parser.parse_args()
    publish(args.work, args.panel, args.results, args.report, args.qualification)
