"""Collect the interleaved CFO work, decision parity and ideal-envelope audit."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median

from ..__main__ import save_json, write
from . import coarse_cfo_eval as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

METHODS = ("full512", "unrepaired", "shortlist", "bounded")
LABELS = ("Full 512", "Projection only", "Shortlist repair", "Interval check + fallback")


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def measurements(work):
    decision, time, work_rows = [], [], []
    for case in trial.CASES:
        for panel in ("held", "unrepaired"):
            data = read(work / f"{case}-{panel}.json.gz")
            for row in data["rows"]:
                label = str(row["visit"]) if "visit" in row else row["control"]
                status = "radio" if "visit" in row else "synthetic"
                for method, outcome in row["comparisons"].items():
                    losses = outcome["accepted"]
                    key = dict(case=case, label=label, panel=panel, status=status, method=method)
                    decision.append(
                        dict(
                            key,
                            exact_installed=outcome["complete_equal"],
                            exact_prepared=outcome["matches_prepared"],
                            ranks=outcome["same_ranked_attempts"],
                            installed_positive=sum(r["production_positive"] for r in losses),
                            lost_positive=sum(r["production_only"] for r in losses),
                            extra_positive=sum(r["native_only"] for r in losses),
                        )
                    )
                    for number, timed in enumerate(row["timing"]):
                        actual, before = (
                            timed["observations"][mode] for mode in (method, "full256")
                        )
                        grids = actual["grid_receipts"]
                        fallback_work = sum(
                            before["grid_receipts"][i]["inverse_ffts"]
                            for i, g in enumerate(grids)
                            if g.get("fallback", False)
                        )
                        time.append(
                            dict(
                                key,
                                repetition=number,
                                first=timed["order"][0] == method,
                                cpu_ms=actual["cpu_ns"] / 1e6,
                                wall_ms=actual["wall_ns"] / 1e6,
                                cpu_delta_ms=(actual["cpu_ns"] - before["cpu_ns"]) / 1e6,
                                wall_delta_ms=(actual["wall_ns"] - before["wall_ns"]) / 1e6,
                                native_grid_cpu_ms=sum(g["native_cpu_ns"] for g in grids) / 1e6,
                                rescore_cpu_ms=sum(g.get("rescore_cpu_ns", 0) for g in grids) / 1e6,
                                inverse_ffts=sum(g["inverse_ffts"] for g in grids) + fallback_work,
                                fallback_inverse_ffts=fallback_work,
                                fallback_grids=sum(g.get("fallback", False) for g in grids),
                            )
                        )
                        work_rows.extend(
                            dict(key, repeat=number, invocation=i, **g) for i, g in enumerate(grids)
                        )
    return decision, time, work_rows


def summarize(decisions, timing, work):
    result = {}
    for mode in METHODS:
        rows = [r for r in decisions if r["status"] == "radio" and r["method"] == mode]
        paired = [r for r in timing if r["status"] == "radio" and r["method"] == mode]
        grids = [r for r in work if r["status"] == "radio" and r["method"] == mode]
        result[mode] = dict(
            visited=len(rows),
            ordered_public_matches=sum(r["exact_installed"] for r in rows),
            full_prepared_matches=sum(r["exact_prepared"] for r in rows),
            acquired_matches=sum(r["ranks"] for r in rows),
            original_positives=sum(r["installed_positive"] for r in rows),
            lost=sum(r["lost_positive"] for r in rows),
            extra=sum(r["extra_positive"] for r in rows),
            paired_calls=len(paired),
            median_cpu_delta_ms=median(r["cpu_delta_ms"] for r in paired),
            median_wall_delta_ms=median(r["wall_delta_ms"] for r in paired),
            median_cpu_ms=median(r["cpu_ms"] for r in paired),
            median_inverse_ffts=median(r["inverse_ffts"] for r in paired),
            grids=len(grids),
            interval_checks_passed=sum(r.get("interval_check", False) for r in grids),
            fallback_grids=sum(r.get("fallback", False) for r in grids),
            median_revisited_cells=median(r.get("revisited_cells", 0) for r in grids),
        )
    return result


def stage_rows(work, summary):
    traces = [
        item for name in trial.DEV for item in read(work / f"{name}-development.json.gz")["traces"]
    ]
    values = []
    for order in ("6", "11"):
        for count in (12, 22):
            series = [
                r["comparisons"][order]["optimistic_required_cells"]
                for r in traces
                if r["anchors"] == count
            ]
            values.append(
                dict(
                    panel="interval",
                    condition=order,
                    arm=str(count),
                    value=median(series),
                    min=min(series),
                    max=max(series),
                    parity="",
                )
            )
    for mode, label in zip(METHODS, LABELS, strict=True):
        row = summary[mode]
        values.append(
            dict(
                panel="held",
                condition=label,
                arm=mode,
                value=row["median_cpu_delta_ms"],
                min="",
                max="",
                parity=f"{row['ordered_public_matches']}/{row['visited']}",
            )
        )
    return values


def chart(root, values):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (a, b) = plt.subplots(1, 2, figsize=(10.9, 4.35), layout="constrained")
    for count, offset, color in (("12", -0.17, "#356a87"), ("22", 0.17, "#487f65")):
        subset = [r for r in values if r["panel"] == "interval" and r["arm"] == count]
        start = [j + offset for j in range(len(subset))]
        a.scatter(start, [r["value"] for r in subset], label=f"{count} anchors", color=color, s=36)
        a.vlines(start, [r["min"] for r in subset], [r["max"] for r in subset], color=color, lw=2)
    a.set_xticks((0, 1), ("Six terms", "Eleven terms"))
    a.set_yscale("log")
    a.set_ylabel("Candidate and neighbor cells")
    a.set_title("Ideal enclosure at the known cutoff", loc="left")
    a.legend(frameon=False)

    held = [r for r in values if r["panel"] == "held"]
    y = list(range(len(held)))
    b.barh(y, [r["value"] for r in held], color=["#6d8190", "#487f65", "#b45a42", "#aa7962"])
    b.set_yticks(y, [f"{r['condition']} · {r['parity']}" for r in held])
    b.invert_yaxis()
    b.axvline(0, color="#555555", lw=1)
    b.set_xlabel("Paired complete CPU change vs full 256 (ms)")
    b.set_title("Held detector timing and exact payloads", loc="left")
    for axe in (a, b):
        axe.spines[["top", "right"]].set_visible(False)
        axe.grid(alpha=0.18)
        axe.set_axisbelow(True)
    fig.savefig(root / "stage.png", dpi=165)
    fig.savefig(root / "stage.pdf", metadata={"CreationDate": None})
    plt.close(fig)


def finish(work, output):
    output.mkdir(parents=True, exist_ok=True)
    decisions, timing, grids = measurements(work)
    summary = summarize(decisions, timing, grids)
    stage = stage_rows(work, summary)
    for source in sorted([*work.glob("DS*.json.gz"), *work.glob("*-lock.json")]):
        write(output / source.name, source.read_bytes())
    for terms in (6, 11):
        directory = work / f"frozen-{terms}"
        for name in (
            "capture_fft.c",
            "folded_bank.c",
            "original_kernel_cache.h",
            "coarse_cfo_fold.h",
            "coarse_cfo.so",
        ):
            write(output / "build" / directory.name / name, (directory / name).read_bytes())
    write(output / "build/coarse_cfo_repair.c", trial.coarse_cfo.DIRECT.read_bytes())
    # Native receipt fields vary between exact, projected and repaired calls.
    save_json(output / "grid-receipts.json", grids)
    save_json(output / "qualification.json", summary)
    for name, values in (("decisions", decisions), ("timing", timing), ("stage", stage)):
        csv_file(output / f"{name}.csv", values)
    chart(output, stage)
    save_json(
        output / "stage-figure.json",
        dict(
            version=1,
            id="interleaved-coarse-cfo",
            title="Interpolate the original coarse CFO grid",
            sample="Two development and six held stereo visits across three capture producers",
            boundary="Complete original coarse timing support through final detector candidates",
            note="Held CPU changes use the full measured-plan 256 bank as the paired comparator. "
            "The enclosure chart uses the original top-eight score threshold on development IQ.",
            seal="stage-figure-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )
    names = ("stage-figure.json", "stage.png", "stage.pdf", "stage.csv")
    save_json(output / "stage-figure-lock.json", dict(files={n: _sha(output / n) for n in names}))
    save_json(
        output / "evidence-lock.json",
        dict(
            files={
                str(p.relative_to(output)): _sha(p)
                for p in sorted(output.rglob("*"))
                if p.is_file() and p.name != "evidence-lock.json"
            }
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    cli = parser.parse_args()
    finish(cli.work, cli.out)
