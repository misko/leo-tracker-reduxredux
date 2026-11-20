"""Seal and chart FFTW block length development and held detector evidence."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median

from ..__main__ import save_json, write
from . import fft_length_sweep as sweep
from .full_v5_check import _sha
from .prefix_figures import csv_file

MODES = ("prepared", "selected")
CAPTION = "Measured development selected a stored-plan 256 bank for complete held detector replay."


def unpack(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def measured(work):
    rows, timings, details = [], [], []
    for case in sweep.HELD:
        evidence = unpack(work / f"{case}-held.json.gz")
        for r in evidence["rows"]:
            label = str(r["visit"]) if "visit" in r else r["control"]
            kind = "radio" if "visit" in r else "synthetic"
            key = dict(case=case, label=label, kind=kind)
            match = r["matching"]
            rows.append(
                dict(
                    key,
                    same_full=r["same_prepared"],
                    same_installed=r["same_installed"],
                    same_coarse_path=r["same_attempts"],
                    same_installed_path=r["same_installed_attempts"],
                    same_ranks=r["same_grid_count"]
                    and all(m["same_ranked_keys"] for m in r["maps"]),
                    candidates=sum(
                        len(rx["candidates"])
                        for rx in r["payloads"]["selected"]["public"]["receivers"]
                    ),
                    gated=sum(m["production_positive"] for m in match),
                    lost=sum(m["production_only"] for m in match),
                    extra=sum(m["native_only"] for m in match),
                )
            )
            details.extend(dict(key, grid=i, **m) for i, m in enumerate(r["maps"]))
            for repeat, pair in enumerate(r["timings"]):
                for arm, data in pair["measurements"].items():
                    timings.append(
                        dict(
                            key,
                            repeat=repeat,
                            arm=arm,
                            first=pair["order"][0] == arm,
                            cpu_ms=data["cpu_ns"] / 1e6,
                            wall_ms=data["wall_ns"] / 1e6,
                            coarse_ms=data["stages_cpu_ns"]["coarse_inclusive"] / 1e6,
                            rss_high_water_kib=data["rss_after"]["hwm_kib"],
                            primary_bytes=max(
                                g["buffer_bytes"]
                                for g in data["grid_receipts"]
                                if g["anchors"] == 12
                            ),
                            retry_bytes=max(
                                (
                                    g["buffer_bytes"]
                                    for g in data["grid_receipts"]
                                    if g["anchors"] == 22
                                ),
                                default=0,
                            ),
                        )
                    )
    return rows, timings, details


def paired(rows):
    trials = {}
    for r in rows:
        if r["kind"] == "radio":
            trials.setdefault((r["case"], r["label"], r["repeat"]), {})[r["arm"]] = r
    return {
        metric: dict(
            saving_ms=median(
                p["prepared"][metric] - p["selected"][metric] for p in trials.values()
            ),
            saving_percent=100
            * median(1 - p["selected"][metric] / p["prepared"][metric] for p in trials.values()),
        )
        for metric in ("cpu_ms", "wall_ms", "coarse_ms")
    }


def plot_data(selection, timings):
    values = []
    for key, label in (("paired_native_ratio", "Estimate"), ("measured_ratios", "Stored measure")):
        for length, ratio in sorted(selection[key].items(), key=lambda x: int(x[0])):
            values.append(
                dict(
                    panel="development",
                    case="",
                    visit="",
                    length=length,
                    arm=label,
                    metric="native_cpu_ratio",
                    value=ratio,
                )
            )
    keys = list(dict.fromkeys((r["case"], r["label"]) for r in timings if r["kind"] == "radio"))
    for case, visit in keys:
        for arm in MODES:
            rows = [r for r in timings if (r["case"], r["label"], r["arm"]) == (case, visit, arm)]
            values.append(
                dict(
                    panel="held",
                    case=case,
                    visit=visit,
                    length=512 if arm == "prepared" else selection["selected"],
                    arm=arm,
                    metric="full_detector_cpu_ms",
                    value=median(r["cpu_ms"] for r in rows),
                )
            )
    return values


def chart(output, values):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (a, b) = plt.subplots(1, 2, figsize=(11.4, 4.35), layout="constrained")
    length = [r["length"] for r in values if r["arm"] == "Estimate"]
    for flavor, delta, color in (
        ("Estimate", -0.17, "#295778"),
        ("Stored measure", 0.17, "#b65b41"),
    ):
        rows = [r for r in values if r["arm"] == flavor]
        a.bar(
            [length.index(r["length"]) + delta for r in rows],
            [r["value"] for r in rows],
            width=0.30,
            color=color,
            label=flavor,
        )
    a.axhline(1, color="#444444", lw=1, ls=":")
    a.set_xticks(range(len(length)), length)
    a.set_xlabel("FFT block length (samples)")
    a.set_ylabel("Paired native CPU / released 512")
    a.set_title("Development sweep", loc="left")
    a.legend(frameon=False)

    base = [r for r in values if r["arm"] == "prepared"]
    for method, name, delta, color in (
        ("prepared", "Released 512", -0.17, "#295778"),
        ("selected", "Measured-plan 256", 0.17, "#b65b41"),
    ):
        rows = [r for r in values if r["arm"] == method]
        b.bar(
            [i + delta for i in range(len(rows))],
            [r["value"] for r in rows],
            width=0.30,
            color=color,
            label=name,
        )
    b.set_xticks(
        range(len(base)),
        [f"{r['case']}\nvisit {r['visit']}" for r in base],
        rotation=29,
        ha="right",
    )
    b.set_ylabel("Median complete detector CPU (ms)")
    b.set_ylim(0, 1.25 * max(r["value"] for r in values if r["panel"] == "held"))
    b.set_title("Held dual-receiver visits", loc="left")
    b.legend(frameon=False, ncols=2, loc="upper center")
    for ax in (a, b):
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.17)
    fig.savefig(output / "stage.png", dpi=165)
    fig.savefig(output / "stage.pdf", metadata=dict(CreationDate=None))
    plt.close(fig)


def finish(work, output):
    output.mkdir(parents=True, exist_ok=True)
    select = json.loads((work / "selection-lock.json").read_bytes())
    freeze = json.loads((work / "held-lock.json").read_bytes())
    decisions, timings, maps = measured(work)
    values = plot_data(select, timings)
    for name in ("input", "estimate-selection", "planning", "selection", "held"):
        source = work / f"{name}-lock.json"
        write(output / source.name, source.read_bytes())
    for source in sorted(work.glob("DS*.json.gz")):
        write(output / source.name, source.read_bytes())
    for length in (256, 512):
        for source in sorted((work / f"planned-{length}").iterdir()):
            write(output / "build" / source.parent.name / source.name, source.read_bytes())
    csv_file(output / "timings.csv", timings)
    csv_file(output / "decisions.csv", decisions)
    csv_file(output / "stage.csv", values)
    save_json(output / "rank-audit.json", maps)
    real = [r for r in decisions if r["kind"] == "radio"]
    checks = [r for r in maps if r["kind"] == "radio"]
    save_json(
        output / "qualification.json",
        dict(
            length=freeze["length"],
            planner=freeze["planner"],
            candidate_sha256=freeze["candidate"]["sha256"],
            radio=len(real),
            synthetic=len(decisions) - len(real),
            full_parity=sum(r["same_full"] for r in real),
            original_parity=sum(r["same_installed"] for r in real),
            coarse_score_cells=sum(r["cells"] for r in checks),
            real_candidate_count=sum(r["candidates"] for r in real),
            real_fractional_positives=sum(r["gated"] for r in real),
            maximum_real_grid_error=max(r["max_error"] for r in checks),
            minimum_real_rank_gap=min(
                r["smallest_prepared_rank_gap"]
                for r in checks
                if r["smallest_prepared_rank_gap"] is not None
            ),
            compared_pairs=sweep.REPEATS * len(real),
            paired_real_improvement=paired(timings),
            mixed_process_rss_high_water_kib=max(r["rss_high_water_kib"] for r in timings),
        ),
    )
    chart(output, values)
    save_json(
        output / "stage-figure.json",
        dict(
            version=1,
            id="prepared-coarse-fft-length",
            title="Choose the prepared coarse FFT length",
            sample="Two development and eight separate held stereo IQ visits",
            boundary="Prepared coarse grid through all accepted and rejected detector candidates",
            note=CAPTION,
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
    parser.add_argument("--out", type=Path, default=sweep.REPORT)
    cli = parser.parse_args()
    finish(cli.work, cli.out)
