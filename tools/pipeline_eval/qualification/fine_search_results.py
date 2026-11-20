"""Publish verified fine CFO search receipts and the complete detector timing chart."""

import argparse
from pathlib import Path
from statistics import median

import matplotlib
import numpy as np

from ..__main__ import local_output, save_json, write
from ..variants import fine_search
from . import fine_search_trial as trial
from .capture_runtime import checked, decompress, read
from .full_v5_check import _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def spread(values):
    return dict(n=len(values), min=min(values), median=median(values), max=max(values))


def comparisons(result, lock, timings, audits):
    as_ms = 1e6
    for sample, fixture in zip(result["rows"], lock["rows"], strict=True):
        if any(sample[key] != fixture[key] for key in ("visit", "iq_sha256", "kind", "probes")):
            raise ValueError("worker output disagrees with the locked archive")
        fine = sample["fine_rows"]
        expected = dict(
            calls=len(fine),
            fallbacks=0,
            frames=sum(r["frames"] for r in fine),
            bins=sum(r["frames"] * r["bins"] for r in fine),
        )
        modes = {mode: [r for r in sample["timings"] if r["mode"] == mode] for mode in trial.MODES}
        for rep, (base, after) in enumerate(zip(*modes.values(), strict=True)):
            if (
                base["coarse_grids"] != after["coarse_grids"]
                or base["repetition"] != after["repetition"]
                or base["repetition"] != rep
                or base["first"] == after["first"]
                or after["fine"] != expected
                or any(base["fine"].values())
            ):
                raise ValueError("timed modes changed repeat or scientific coverage")
            timings.append(
                dict(
                    visit=sample["visit"],
                    repetition=rep,
                    row_wise_cpu_ms=base["cpu_ns"] / as_ms,
                    pruned_cpu_ms=after["cpu_ns"] / as_ms,
                    row_wise_wall_ms=base["wall_ns"] / as_ms,
                    pruned_wall_ms=after["wall_ns"] / as_ms,
                )
            )
        if len(modes["row_wise"]) != trial.REPEATS:
            raise ValueError("timed call is missing")
        public = [c for rx in sample["public"]["receivers"] for c in rx["candidates"]]
        factors = [c for rx in sample["probes"] for c in rx["candidates"]]
        audits.append(
            dict(
                visit=sample["visit"],
                kind=sample["kind"],
                public_candidates=len(public),
                integer_pass=sum(c["passed_margin_gate"] for c in public),
                projected_candidates=len(factors),
                fractional_pass=sum(c["passed_fractional_margin_gate"] for c in factors),
                paired_repeats=trial.REPEATS,
                factor_rows=len(sample["probes"]),
                nearest_gate=min(
                    abs(c["fractional_margin"] - trial.previous.GATE)
                    for c in factors
                    if c["fractional_margin"] is not None
                ),
                min_fine_gap=min(r["best_minus_second"] for r in fine),
                requested_bins=sorted({r["bins"] for r in fine}),
                evaluated=expected,
                row_wise_fine_cpu_ms=sum(r["original_cpu_ns"] for r in fine) / as_ms,
                pruned_fine_cpu_ms=sum(r["pruned_cpu_ns"] for r in fine) / as_ms,
            )
        )


def paired(rows, kind):
    changes = [r[f"row_wise_{kind}_ms"] - r[f"pruned_{kind}_ms"] for r in rows]
    return spread(changes) | {
        "median_percent": 100
        * median(saved / r[f"row_wise_{kind}_ms"] for saved, r in zip(changes, rows, strict=True))
    }


def chart(folder, results):
    labels = [f"{name}\n{row['edge']}" for name, row in results.items()]
    ypos = np.arange(len(labels))
    fig, axes = plt.subplots(ncols=2, figsize=(10, 4.4), layout="constrained", sharey=True)
    configs = (
        ("Complete detector", "cpu_ms", "20 timed calls per arm"),
        ("Fine CFO scoring", "fine_cpu_ms", "4 independently audited visits per arm"),
    )
    for axis, (title, column, context) in zip(axes, configs, strict=True):
        for mode, label, offset, color in (
            ("row_wise", "Original fine FFT", -0.16, "#405a77"),
            ("pruned", "Pruned fine FFT", 0.16, "#087a70"),
        ):
            rows = [r[f"{mode}_{column}"] for r in results.values()]
            mid = np.array([r["median"] for r in rows])
            left = mid - [r["min"] for r in rows]
            right = [r["max"] for r in rows] - mid
            axis.errorbar(
                mid,
                ypos + offset,
                xerr=[left, right],
                fmt="o",
                capsize=3,
                color=color,
                label=label,
            )
        axis.set_title(f"{title}\n{context}", pad=11)
        axis.set_xlabel("Process CPU time per dual visit (ms)")
        axis.set_yticks(ypos, labels)
        axis.grid(axis="x", color="#dee4ea")
        axis.set_axisbelow(True)
    axes[0].invert_yaxis()
    handles, descriptions = axes[1].get_legend_handles_labels()
    fig.legend(handles, descriptions, loc="outside lower center", ncols=2, frameon=False)
    fig.suptitle("Fine CFO prefix transform on saved capture IQ", fontsize=13)
    for extension in ("png", "pdf"):
        fig.savefig(folder / f"stage.{extension}", dpi=160)
    plt.close(fig)


def report(work, folder):
    lockfile = work / "input-lock.json"
    lock = read(lockfile)
    for path, digest in lock["sources"].items():
        checked(Path(path), digest)
    write(folder / lockfile.name, lockfile.read_bytes())
    cases, timings, audits = {}, [], []
    for name, cfg in lock["cases"].items():
        receipt = work / f"{name}.json.gz"
        row = decompress(receipt)
        if row["input_lock_sha256"] != _sha(lockfile):
            raise ValueError("worker was bound to a different input lock")
        write(folder / receipt.name, receipt.read_bytes())
        elapsed, score_times = [], []
        comparisons(row, cfg, elapsed, score_times)
        timings.extend(dict(r, case=name) for r in elapsed)
        audits.extend(dict(r, case=name) for r in score_times)
        cases[name] = dict(
            edge=cfg["edge"],
            paired_cpu_ms=paired(elapsed, "cpu"),
            paired_wall_ms=paired(elapsed, "wall"),
            peak_rss_kib=row["peak_rss_kib"],
            workspace_bytes=row["workspace_bytes"],
            rotation_cache=row["rotation_cache"],
            **{
                key: spread([r[key] for r in group])
                for key, group in (
                    ("row_wise_cpu_ms", elapsed),
                    ("pruned_cpu_ms", elapsed),
                    ("row_wise_wall_ms", elapsed),
                    ("pruned_wall_ms", elapsed),
                    ("row_wise_fine_cpu_ms", score_times),
                    ("pruned_fine_cpu_ms", score_times),
                )
            },
        )
    summary = dict(
        cases=cases,
        paired_cpu_ms=paired(timings, "cpu"),
        paired_wall_ms=paired(timings, "wall"),
        audits=audits,
        timing=timings,
        source_lines={
            p.name: len(p.read_text().splitlines())
            for p in (Path(fine_search.__file__), fine_search.SOURCE)
        },
        source_bytes={
            p.name: p.stat().st_size for p in (Path(fine_search.__file__), fine_search.SOURCE)
        },
        binary_bytes=Path(lock["libs"]["fine"]["path"]).stat().st_size,
    )
    save_json(folder / "summary.json", summary)
    chart(folder, cases)
    save_json(
        folder / "qualification-lock.json",
        dict(
            files={
                p.name: _sha(p)
                for p in folder.iterdir()
                if p.name not in ("README.md", "qualification-lock.json") and p.is_file()
            },
            report_generator_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    report(args.work, trial.REPORT)
