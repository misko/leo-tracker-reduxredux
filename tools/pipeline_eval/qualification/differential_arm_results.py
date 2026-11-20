"""Report portable scout parity and keep guest clocks separate from process overhead."""

import argparse
import csv
import json
import subprocess
from pathlib import Path
from statistics import median
from time import monotonic, sleep

import matplotlib

from ..__main__ import save_json
from . import differential_arm as trial
from .full_v5_check import _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

MODES = ("host", "arm")
CLOCKS = ("cpu_ns", "wall_ns")
MEMORY_FIXTURES = ("DS26-0162:19", "lower-one-frame")


def memory_probe(work):
    lock = trial.authenticated(work)
    result = {}
    for tag in MEMORY_FIXTURES:
        item = lock["inputs"][tag]
        payload = work / item["file"]
        if _sha(payload) != item["sha256"]:
            raise ValueError("memory probe input is unavailable or changed")
        edge = item["edge"]
        observations = {}
        for mode in MODES:
            launcher = (trial.QEMU, "-cpu", "cortex-a9") if mode == "arm" else ()
            native = work / lock["libraries"][mode]["file"]
            argv = (
                *launcher,
                native,
                payload,
                work / f"{edge}-filters.c8",
                work / f"{edge}-energies.f64",
                "8",
            )
            executable = (trial.QEMU if launcher else native).resolve()
            peaks, polls = {}, 0
            with subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as proc:
                expires = monotonic() + 15
                status = Path(f"/proc/{proc.pid}/status")
                while proc.poll() is None:
                    if monotonic() >= expires:
                        proc.kill()
                        raise TimeoutError("process-memory replay exceeded 15 seconds")
                    try:
                        if status.with_name("exe").resolve(strict=True) == executable:
                            fields = {
                                line[0][:-1]: int(line[1])
                                for line in map(str.split, status.read_text().splitlines())
                                if len(line) >= 2 and line[0] in ("VmHWM:", "VmRSS:", "VmPeak:")
                            }
                            for field, value in fields.items():
                                peaks[field] = max(peaks.get(field, 0), value)
                            polls += 1
                    except (FileNotFoundError, ProcessLookupError):
                        pass
                    sleep(0.002)
                stderr = proc.stderr.read()
                if proc.returncode or not peaks:
                    raise RuntimeError(f"memory observation did not complete: {stderr!r}")
            observations[mode] = dict(polls=polls, maximum_kib=peaks)
        result[tag] = observations
    save_json(
        work / "memory.json",
        dict(fixtures=result, note="/proc of executed process only; timing kept separate"),
    )


def summarize(folder):
    measurement = json.loads((folder / "measurements.json").read_bytes())
    lock_path = folder / "source-lock.json"
    if measurement["source_lock_sha256"] != _sha(lock_path):
        raise ValueError("result and source lock identity differ")
    lock = json.loads(lock_path.read_bytes())
    rows = measurement["results"]
    combined, csv_rows = {}, []
    for mode in MODES:
        values = [r[mode] for r in rows.values()]
        categories = {k: [r[k] for r in values] for k in ("read_prepare", "fftw_context")}
        for key in ("scoring", "ranking"):
            categories[f"first_{key}"] = [r["calls"][0][key] for r in values]
            categories[f"warm_{key}"] = [c[key] for r in values for c in r["calls"][1:]]
        combined[mode] = {
            k: {
                clock.removesuffix("_ns"): median(r[clock] / 1e6 for r in series)
                for clock in CLOCKS
            }
            for k, series in categories.items()
        }
        combined[mode]["external_full_process_ms"] = {
            name: median(r[f"external_{name}_ns"] / 1e6 for r in values) for name in ("cpu", "wall")
        }
        for tag, item in rows.items():
            for call_index, call in enumerate(item[mode]["calls"], 1):
                csv_rows.append(
                    dict(
                        fixture=tag,
                        edge=item["input"]["edge"],
                        kind=item["input"]["role"],
                        architecture=mode,
                        call=call_index,
                        both_full_ranks_equal=all(item["rank_complete_parity"]),
                        grid_exact=item["host"]["full_grid_sha256"]
                        == item["arm"]["full_grid_sha256"],
                        context_cpu_ms=item[mode]["fftw_context"]["cpu_ns"] / 1e6,
                        scorer_cpu_ms=call["scoring"]["cpu_ns"] / 1e6,
                        scorer_wall_ms=call["scoring"]["wall_ns"] / 1e6,
                        ranking_cpu_ms=call["ranking"]["cpu_ns"] / 1e6,
                        ranking_wall_ms=call["ranking"]["wall_ns"] / 1e6,
                    )
                )
    with (folder / "stage.csv").open("w", newline="") as stream:
        table = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        table.writeheader()
        table.writerows(csv_rows)

    summary = dict(
        windows=len(rows),
        lanes=2 * len(rows),
        cells=26_666 * len(rows),
        score_grids_exact=sum(
            r["arm"]["full_grid_sha256"] == r["host"]["full_grid_sha256"] for r in rows.values()
        ),
        ordered_top16_equal=sum(sum(r["rank_complete_parity"]) for r in rows.values()),
        numpy_ordered_top16_equal=sum(sum(r["arm_matches_python"]) for r in rows.values()),
        host_windows_exact_to_prior_ranks=sum(r["host_matches_previous"] for r in rows.values()),
        arm_numpy_relative_linf=max(v for r in rows.values() for v in r["arm_vs_numpy_rel_linf"]),
        timing_median_ms=combined,
        qemu=lock["qemu_version"],
        affinity=measurement["affinity"],
        boundary="standalone scout and top-16 before wide GLRT, Cortex-A9 emulation",
    )
    save_json(folder / "summary.json", summary)
    return summary


def chart(folder, summary):
    report = summary["timing_median_ms"]
    stages = ("read_prepare", "fftw_context", "first_scoring", "warm_scoring", "warm_ranking")
    labels = ("Load / validate", "FFTW context", "First score", "Warm score", "Warm rank")
    fig, ax = plt.subplots(figsize=(9.8, 4.5))
    colors = {"host": "#355d77", "arm": "#087e6c"}
    for key, label, step in (
        ("host", "Native x86-64", -0.18),
        ("arm", "ARMv7 in Cortex-A9 QEMU", 0.18),
    ):
        timing = [report[key][stage]["cpu"] for stage in stages]
        x = [i + step for i in range(len(stages))]
        ax.bar(x, timing, width=0.33, color=colors[key], label=label)
        for position, value in zip(x, timing, strict=True):
            ax.text(position, value * 1.16, f"{value:.2f}", ha="center", va="bottom", fontsize=8)
    ax.set_yscale("log")
    ax.set_ylim(0.18, 165)
    ax.set_xticks(range(len(stages)), labels)
    ax.set_ylabel("Median process CPU (ms, log scale)")
    ax.grid(axis="y", alpha=0.22)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, frameon=False)
    fig.suptitle(
        "Differential FFTW scout on the ARMv7 ABI",
        x=0.095,
        y=0.986,
        ha="left",
        fontweight="bold",
        fontsize=16,
    )
    fig.text(
        0.095,
        0.89,
        "3 genuine and 8 control windows. 22/22 ordered top-16 lists match. No hardware timing.",
        fontsize=10,
    )
    fig.subplots_adjust(left=0.095, right=0.98, bottom=0.22, top=0.82)
    fig.savefig(folder / "stage.png", dpi=175)
    fig.savefig(folder / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def report(folder):
    summary = summarize(folder)
    chart(folder, summary)
    names = (
        "source-lock.json",
        "measurements.json",
        "memory.json",
        "differential-armv7.tar.gz",
        "summary.json",
        "stage.csv",
        "stage.png",
        "stage.pdf",
    )
    save_json(
        folder / "result-lock.json",
        dict(
            files={name: _sha(folder / name) for name in names},
            source_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("memory", "report"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    if args.mode == "memory":
        memory_probe(args.folder)
    else:
        report(args.folder)
