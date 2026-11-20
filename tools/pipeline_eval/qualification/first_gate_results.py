"""Publish the authenticated complete-detector timing and ranked work ledger."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median

import matplotlib

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import first_gate_trial as trial
from .full_v5_check import _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


def summarize(timings, attempts):
    result = {}
    for mode in trial.MODES:
        candidates = attempts[mode]
        result[mode] = dict(
            physical_attempts=len(candidates),
            retries=sum(row["retry"] for row in candidates),
            available=sum(row["available"] for row in candidates),
            evaluated=sum(row["scored"] for row in candidates),
            attempts_shortened=sum(row["available"] > row["scored"] for row in candidates),
            fractional_passes=sum(len(row["passing_ranks"]) for row in candidates),
        )
        for clock in ("cpu", "wall"):
            key = f"{clock}_ns"
            sample = [rep[mode][key] / 1e6 for rep in timings]
            savings = [(rep["full"][key] - rep[mode][key]) / 1e6 for rep in timings]
            ratios = [100 * (1 - rep[mode][key] / rep["full"][key]) for rep in timings]
            result[mode][clock] = dict(
                min_ms=min(sample),
                median_ms=median(sample),
                max_ms=max(sample),
                pairs=len(sample),
                median_paired_ms=median(savings),
                median_paired_percent=median(ratios),
            )
    return result


def records(result, cfg, source_digest, name):
    if (result["id"], result["cpu"], result["input_lock_sha256"]) != (
        name,
        cfg["cpu"],
        source_digest,
    ):
        raise ValueError("worker output differs from the frozen panel")
    timings, attempts = [], {mode: [] for mode in trial.MODES}
    for row, fixture in zip(result["rows"], cfg["rows"], strict=True):
        if any(row[key] != fixture[key] for key in ("visit", "iq_sha256", "kind")):
            raise ValueError("unexpected held IQ")
        for m, values in row["attempts"].items():
            if len(values) != len(row["attempts"]["full"]):
                raise ValueError("ranked stop changed the original attempt schedule")
            for actual, stock in zip(values, row["attempts"]["full"], strict=True):
                passing = stock["passing_ranks"][: trial.MODES[m]]
                if len(passing) == trial.MODES[m]:
                    expected = [r for r in stock["retained_ranks"] if r <= passing[-1]]
                else:
                    expected = stock["retained_ranks"]
                if (
                    any(actual[k] != stock[k] for k in ("receiver", "probe", "retry", "available"))
                    or actual["scored"] != len(expected)
                    or actual["retained_ranks"] != expected
                    or actual["passing_ranks"] != passing
                ):
                    raise ValueError("received attempt tally does not implement the rank cutoff")
            attempts[m].extend(values)
        for rep in range(trial.REPEATS):
            samples = [s for s in row["samples"] if s["rep"] == rep]
            if (
                {s["mode"] for s in samples} != trial.MODES.keys()
                or sorted(s["ordinal"] for s in samples) != list(range(len(trial.MODES)))
                or any(
                    s[k] != samples[0][k]
                    for s in samples
                    for k in ("coarse_grids", "fine_calls", "fine_fallbacks")
                )
            ):
                raise ValueError("unmatched chronological repeat or acquisition work changed")
            timings.append({s["mode"]: s for s in samples})
    return timings, attempts


def chart(folder, rows):
    fig, axes = plt.subplots(ncols=2, figsize=(11.2, 4.8), layout="constrained", sharey=True)
    labels = [f"{name} · {result['edge']}" for name, result in rows.items()]
    y = list(range(len(rows)))
    styles = (
        ("full", "All ranks", -0.2, "#405a77"),
        ("first", "Stop after first pass", 0, "#087a70"),
        ("second", "Stop after second pass", 0.2, "#bb6535"),
    )
    for ax, clock, title in zip(
        axes, ("cpu", "wall"), ("Process CPU", "Elapsed wall"), strict=True
    ):
        for mode, text, offset, color in styles:
            points = [r["modes"][mode][clock] for r in rows.values()]
            medians = [r["median_ms"] for r in points]
            ranges = [
                [r["median_ms"] - r["min_ms"] for r in points],
                [r["max_ms"] - r["median_ms"] for r in points],
            ]
            ax.errorbar(
                medians,
                [v + offset for v in y],
                xerr=ranges,
                fmt="o",
                ms=5,
                capsize=3,
                color=color,
                label=text,
            )
        ax.set_title(title)
        ax.set_xlabel("Complete dual-visit detector time (ms)")
        ax.set_yticks(y, labels)
        ax.grid(axis="x", color="#dee4ea")
        ax.set_axisbelow(True)
    axes[0].invert_yaxis()
    handles, names = axes[1].get_legend_handles_labels()
    fig.legend(handles, names, loc="outside lower center", ncols=3, frameon=False)
    fig.suptitle(
        "Ranked fractional GLRT stop on saved I/Q\n"
        "Median and range of 20 matched repeats per recording"
    )
    for extension in ("png", "pdf"):
        fig.savefig(folder / f"stage.{extension}", dpi=160)
    plt.close(fig)


def publish(work, folder):
    path = whole_iq.checked(work / "input-lock.json", _sha(folder / "input-lock.json"))
    lock = whole_iq.read(path)
    for source, digest in lock["sources"].items():
        whole_iq.checked(Path(source), digest)
    cases, pooled_timings = {}, []
    pooled_attempts = {mode: [] for mode in trial.MODES}
    for name, cfg in lock["cases"].items():
        receipt = work / f"{name}.json.gz"
        result = json.loads(gzip.decompress(receipt.read_bytes()))
        timings, attempts = records(result, cfg, _sha(path), name)
        pooled_timings.extend(timings)
        for mode in pooled_attempts:
            pooled_attempts[mode].extend(attempts[mode])
        cases[name] = dict(edge=cfg["edge"], modes=summarize(timings, attempts))
        write(folder / receipt.name, receipt.read_bytes())
    save_json(
        folder / "summary.json",
        dict(
            recordings=cases,
            pooled=summarize(pooled_timings, pooled_attempts),
            held_visits=sum(len(cfg["rows"]) for cfg in lock["cases"].values()),
            same_original_coarse_fine_work=True,
            exact_physical_attempt_prefix=True,
        ),
    )
    chart(folder, cases)
    names = (
        "PROTOCOL.md",
        "input-lock.json",
        "summary.json",
        "stage.pdf",
        "stage.png",
        *(f"{name}.json.gz" for name in lock["cases"]),
    )
    save_json(
        folder / "qualification-lock.json",
        dict(
            files={name: _sha(folder / name) for name in names},
            report_generator_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    publish(parser.parse_args().work, trial.REPORT)
