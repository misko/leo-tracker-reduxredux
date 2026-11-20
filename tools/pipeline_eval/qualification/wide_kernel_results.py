"""Verify sealed wide detector receipts and render the paired stage evidence offline."""

import argparse
import io
from collections import Counter
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import distribution
from . import scout_stage_figures as stage
from . import wide_kernel_eval as run
from .prefix_figures import csv_file


def timings(ident, row):
    for mode, trials in row["timings"].items():
        if len(trials) != 9:
            raise ValueError("matched visit does not have its nine warm repetitions")
        for index, trial in enumerate(trials, 1):
            phases = {key: sum(rx[key] for rx in trial["rows"]) for key in trial["rows"][0]}
            yield dict(
                id=ident,
                cohort=row["cohort"],
                visit=row["visit"],
                repetition=index,
                detector=mode,
                native_cpu_ms=trial["detector_cpu_ms"],
                cpu_ms=trial["python_cpu_ms"],
                wall_ms=trial["wall_ms"],
                **{f"{key}_cpu_ms": value for key, value in phases.items()},
            )


def summary(records):
    work = Counter()
    for _, row in records:
        work.update(row["instrumented_work"])
    rows = [row for ident, rec in records for row in timings(ident, rec)]
    table = {}
    keys = (
        "native_cpu_ms",
        "cpu_ms",
        "wall_ms",
        "fractional_epoch_cpu_ms",
        "proposal_cpu_ms",
        "coarse_cpu_ms",
        "acquisition_cpu_ms",
        "fine_fft_cpu_ms",
        "glrt_cpu_ms",
    )
    per_mode = {k: [row for row in rows if row["detector"] == k] for k in run.MODES}
    for mode, group in per_mode.items():
        table[mode] = dict(
            calls=len(group),
            **{key: distribution([r[key] for r in group]) for key in keys},
            deadline={key: sum(r[key] <= 20 for r in group) for key in keys[:3]},
        )
    pairs = list(zip(*(per_mode[k] for k in run.MODES), strict=True))
    matched = {key: distribution([b[key] - a[key] for a, b in pairs]) for key in keys}
    return dict(
        visits=len(records),
        exact_payloads=sum(row["exact"] for _, row in records),
        candidates=sum(
            r["candidate_count"] for _, row in records for r in row["payloads"]["control"]["rows"]
        ),
        positives=sum(len(rx) for _, r in records for rx in r["positives"]["control"]),
        measurements=table,
        paired_candidate_minus_control_ms=matched,
        median_paired_native_cpu_change_pct=median(
            100 * (b["native_cpu_ms"] / a["native_cpu_ms"] - 1) for a, b in pairs
        ),
        operations=dict(work),
    ), rows


def summarize():
    lock = run.load(run.REPORT / "source-lock.json")
    digest = run._digest(encoded(lock))
    if any(run._sha(ROOT / p) != sha for p, sha in lock["source_files"].items()):
        raise ValueError("stored source does not match the fixed visit protocol")
    samples, invalid, controls = [], [], {}
    for ident in run.CASES:
        data = run.load(run.REPORT / f"{ident}.json.gz")
        if data["id"] != ident or data["source_lock_sha256"] != digest:
            raise ValueError("the replay does not match its frozen input schedule")
        for row, locked in zip(data["rows"], lock["cases"][ident], strict=True):
            if any(row[k] != value for k, value in locked.items()):
                raise ValueError("a scheduled visit or recording bound value changed")
            (samples if row["status"] == "processed" else invalid).append((ident, row))
        if data["controls"]:
            controls[ident] = {
                case: dict(
                    tones=measured["tones"],
                    exact=measured["exact"],
                    by_receiver_positives=measured["positives"],
                    instrumented_work=measured["instrumented_work"],
                )
                for case, measured in data["controls"].items()
            }
    all_rows, csv = summary(samples)
    return dict(
        position_attempted=False,
        scheduled_visits=len(samples) + len(invalid),
        exclusions=[dict(row, id=ident) for ident, row in invalid],
        measurements=all_rows,
        controls=controls,
        release=lock["release"],
        cohorts={
            name: summary([(i, r) for i, r in samples if r["cohort"] == name])[0]
            for name in ("held", "cpu-tail")
        },
        cpu_tail=[
            dict(
                id=i,
                visit=r["visit"],
                admitted_control_cpu_ms=r["old_cpu_s"] * 1000,
                paired_native_cpu_ms={
                    k: median(q["detector_cpu_ms"] for q in r["timings"][k]) for k in run.MODES
                },
            )
            for i, r in samples
            if r["cohort"] == "cpu-tail"
        ],
    ), csv


def render(data, out):
    result = data["measurements"]
    fig, (stages, rates) = stage.canvas(
        "Batching adjacent samples in the wide detector",
        f"{result['visits']} authenticated dual-RX visits · nine matched warm repeats · host x86",
        "The released 21-bin detector retains all four scout regions and all final gates. "
        f"Public payloads agreed exactly on {result['exact_payloads']}/{result['visits']} visits. "
        "The deadline uses complete detector wall time. This chart stops at detector output.",
    )
    fig.subplots_adjust(bottom=0.281)
    measures = result["measurements"]
    names = ("Native detector", "Fractional GLRT", "Coarse CFO grid", "Fine FFT")
    keys = ("native_cpu_ms", "fractional_epoch_cpu_ms", "coarse_cpu_ms", "fine_fft_cpu_ms")
    stage.paired(
        stages,
        names,
        [tuple(measures[m][k]["p50"] for m in run.MODES) for k in keys],
        title="Native phase clocks",
        xlabel="Median CPU (ms)",
    )
    groups = (result, data["cohorts"]["held"], data["cohorts"]["cpu-tail"])
    names = ("All admitted visits", "Frozen held visits", "Most expensive\nprior CPU visits")
    percentages = []
    for group in groups:
        percentages.append(
            tuple(
                100
                * group["measurements"][m]["deadline"]["wall_ms"]
                / group["measurements"][m]["calls"]
                for m in run.MODES
            )
        )
    stage.paired(
        rates,
        names,
        percentages,
        title="20 ms wall deadline",
        xlabel="Complete detector calls meeting deadline (%)",
        xmax=120,
        fmt=".1f",
    )
    stage.key(fig, "Released wide detector", "Adjacent fractional sample batch")
    fig.legends[-1].set_bbox_to_anchor((0.052, 0.149))
    for ext in ("png", "pdf"):
        buffer = io.BytesIO()
        options = {"dpi": 165} if ext == "png" else {"metadata": {"CreationDate": None}}
        fig.savefig(buffer, format=ext, facecolor="white", **options)
        write(out / f"wide-kernel.{ext}", buffer.getvalue())
    stage.plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=local_output, default=run.REPORT)
    out = p.parse_args().out
    data, csv = summarize()
    save_json(out / "qualification.json", data)
    csv_file(out / "timing.csv", csv)
    render(data, out)
    names = ["qualification.json", "timing.csv", "wide-kernel.png", "wide-kernel.pdf"]
    if out == run.REPORT:
        names += [
            "PROTOCOL.md",
            "source-lock.json",
            "preflight-source-lock.json",
            "scalar-fallback.json",
            "release.json",
            "build-receipt.json",
            "trace-receipt.json",
            *(f"{i}.json.gz" for i in run.CASES),
        ]
    save_json(
        out / "evidence-lock.json",
        dict(
            cases=list(run.CASES),
            files={name: run._sha(out / name) for name in names},
            scorer_sha256=run._sha(Path(__file__)),
            position_attempted=False,
            scalar_test_sha256=run._sha(Path(__file__).with_name("wide_kernel_compat.py")),
        ),
    )


if __name__ == "__main__":
    main()
