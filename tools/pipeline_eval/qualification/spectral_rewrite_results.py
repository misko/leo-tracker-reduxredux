"""Publish full original detector, spectral profile and memory comparisons."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median

from matplotlib import pyplot as plt

from ..__main__ import local_output, save_json, write
from ..scoring import distribution
from . import spectral_rewrite_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .scout_stage_figures import canvas

LABELS = {"stock": "Original paired", "split": "Unpruned split", "batched": "Batched workspace"}
COLORS = {"stock": "#707C83", "split": "#47739B", "batched": "#146C5F"}


def compressed(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def receipts(work, plan):
    samples, profiles, memory, check = [], [], [], []
    for ident, case in plan["cases"].items():
        full = compressed(work / f"{ident}.json.gz")
        for row, fixture in zip(full, case["rows"], strict=True):
            if any(row[k] != fixture[k] for k in ("visit", "kind", "iq_sha256")):
                raise ValueError("resident timing contains an unexpected physical visit")
            common = dict(id=ident, visit=row["visit"], kind=row["kind"], cpu_pin=case["cpu"])
            published = {}
            for item in row["attempts"]:
                published[item["mode"]] = item["receiver_attempts"]
            if set(published) != set(trial.MODES) or any(
                values != published["stock"] for values in published.values()
            ):
                raise ValueError("a detector mode changed an original attempt fingerprint")
            attempts = published["stock"]
            check.append(
                dict(
                    **common,
                    public_and_native_sha256=row["output_sha256"],
                    attempts=len(attempts),
                    retries=sum(a["retry"] for a in attempts),
                    original_candidates=sum(a["available"] for a in attempts),
                    fractional_passing_candidates=sum(len(a["passing_ranks"]) for a in attempts),
                )
            )
            if len(row["samples"]) != plan["repeats"] * len(trial.MODES) or len(
                row["profiles"]
            ) != len(trial.MODES):
                raise ValueError("timing ledger lacks an original detector call")
            samples.extend(dict(**common, **sample) for sample in row["samples"])
            profiles.extend(
                dict(
                    **common,
                    **sample,
                    spectrum_cpu_pct=100 * sample["spectrum_cpu_ns"] / sample["cpu_ns"],
                )
                for sample in row["profiles"]
            )
        tie = next(r for r in full if r["kind"] == "passing-tie")
        for method in trial.MODES:
            (observed,) = compressed(work / f"{ident}-memory-{method}.json.gz")
            if any(observed[k] != tie[k] for k in ("visit", "iq_sha256", "output_sha256")):
                raise ValueError("independent memory process used a different saved tie visit")
            memory.append(
                dict(
                    id=ident,
                    visit=tie["visit"],
                    mode=method,
                    peak_rss_before_detector_kib=observed["before_memory_kib"],
                    peak_rss_after_detector_kib=observed["detector_peak_rss_kib"],
                    peak_rss_increase_kib=observed["detector_peak_rss_kib"]
                    - observed["before_memory_kib"],
                    workspace_bytes=observed["workspace_bytes"],
                )
            )
    return samples, profiles, memory, check


def summarize(samples, profiles, cases):
    rows = []
    for ident in ("all", *cases):
        timings = [r for r in samples if ident == "all" or r["id"] == ident]
        profile = [r for r in profiles if ident == "all" or r["id"] == ident]
        index = {(r["id"], r["visit"], r["repetition"], r["mode"]): r for r in timings}
        if len(index) != len(timings):
            raise ValueError("duplicated timing in the same matched detector batch")
        stock = [r for r in timings if r["mode"] == "stock"]
        for method in trial.MODES:
            shoulder = [r for r in profile if r["mode"] == method]
            candidate = [index[(r["id"], r["visit"], r["repetition"], method)] for r in stock]
            row = dict(
                id=ident,
                mode=method,
                paired=len(candidate),
                profiled=len(shoulder),
                spectrum_calls=sum(r["spectrum_calls"] for r in shoulder),
                median_spectrum_cpu_ms=median(r["spectrum_cpu_ns"] / 1e6 for r in shoulder),
                total_spectrum_cpu_pct=100
                * sum(r["spectrum_cpu_ns"] for r in shoulder)
                / sum(r["cpu_ns"] for r in shoulder),
                workspace_bytes=max(r["workspace_bytes"] for r in shoulder),
            )
            for clock in ("cpu", "wall"):
                key = f"{clock}_ns"
                both = [(a[key], b[key]) for a, b in zip(stock, candidate, strict=True)]
                p = distribution([b / 1e6 for a, b in both])
                row.update(
                    {
                        f"median_{clock}_ms": p["p50"],
                        f"p95_{clock}_ms": p["p95"],
                        f"median_paired_{clock}_saved_ms": median(a - b for a, b in both) / 1e6,
                        f"median_paired_{clock}_saved_pct": median(
                            100 * (a - b) / a for a, b in both
                        ),
                        f"total_{clock}_saved_pct": 100
                        * sum(a - b for a, b in both)
                        / sum(a for a, b in both),
                    }
                )
            rows.append(row)
    return rows


def plot(report, results, cases, evidence):
    fig, axes = canvas(
        "Reusing the original exact and control spectra",
        "Twenty resident stereo visits · three capture producers",
        "Complete detector timing starts with saved IQ in memory. The spectral share is "
        "measured in separately profiled calls with all original candidate fields.",
    )
    labels = ["All matched visits", *cases]
    by = {(r["id"], r["mode"]): r for r in results}
    for index, mode in enumerate(trial.MODES):
        y = [i + (index - 1) * 0.22 for i in range(len(labels))]
        entries = [by[ident, mode] for ident in ("all", *cases)]
        if mode != "stock":
            axes[0].barh(
                y,
                [r["median_paired_cpu_saved_ms"] for r in entries],
                height=0.18,
                color=COLORS[mode],
            )
        axes[1].barh(
            y,
            [r["total_spectrum_cpu_pct"] for r in entries],
            height=0.18,
            color=COLORS[mode],
            label=LABELS[mode],
        )
    axes[0].axvline(0, color="#495B64", linewidth=0.8)
    for axis, title, xlabel in zip(
        axes,
        ("Complete detector CPU", "CPU in the spectral seam"),
        ("Median paired CPU saved (ms)", "Share of total profiled detector CPU (%)"),
        strict=True,
    ):
        axis.set(title=title, xlabel=xlabel, yticks=range(len(labels)), yticklabels=labels)
        axis.invert_yaxis()
    handles, names = axes[1].get_legend_handles_labels()
    fig.legend(
        handles,
        names,
        loc="lower center",
        bbox_to_anchor=(0.55, 0.125),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    for ext in ("png", "pdf"):
        fig.savefig(
            report / f"stage.{ext}",
            dpi=160,
            metadata={"CreationDate": None} if ext == "pdf" else {},
        )
    plt.close(fig)
    names = (*evidence, "stage.png", "stage.pdf")
    save_json(
        report / "stage-figure-lock.json",
        dict(cases=cases, files={n: _sha(report / n) for n in names}),
    )
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="spectral-rewrite",
            title="Reusing the original exact and control spectra",
            boundary="Resident original detector with complete public output",
            sample="Twenty physical stereo visits from four recordings",
            note="Whole calls include setup and both references.",
            seal="stage-figure-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="summary.csv",
        ),
    )


def publish(work):
    report = trial.REPORT
    plan = trial.read(trial.checked(work / "input-lock.json", _sha(report / "input-lock.json")))
    for path, fingerprint in plan["sources"].items():
        trial.checked(Path(path), fingerprint)
    cases = list(plan["cases"])
    samples, profiles, memory, parity = receipts(work, plan)
    summary = summarize(samples, profiles, cases)
    tables = ("timing.csv", "profile.csv", "memory.csv", "attempts.csv", "summary.csv")
    for file, rows in zip(tables, (samples, profiles, memory, parity, summary), strict=True):
        csv_file(report / file, rows)
    inputs = tuple(sorted(work.glob("*.json.gz")))
    names = tuple(f"receipts/{p.name}" for p in inputs)
    for source, target in zip(inputs, names, strict=True):
        write(report / target, source.read_bytes())
    save_json(
        report / "qualification-lock.json",
        dict(
            cases=cases,
            exporter_sha256=_sha(Path(__file__)),
            files={
                name: _sha(report / name)
                for name in ("input-lock.json", "PROTOCOL.md", *tables, *names)
            },
        ),
    )
    plot(report, summary, cases, (*tables, "qualification-lock.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    publish(parser.parse_args().work)
