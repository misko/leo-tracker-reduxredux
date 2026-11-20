"""Fit and seal actual held band-cache factors against the complete ordinary controls."""

import argparse
import gzip
import json
from pathlib import Path
from statistics import median
from unittest.mock import patch

from ..__main__ import encoded, local_output, save_json, write
from ..variants import iq_stream
from . import iq_joint_trial, ordinary_front_position, ordinary_glrt_eval
from .full_v5_check import NATIVE_LIBRARY, _sha
from .ordinary_front_build import ARM_CONTROL

REPORT = ordinary_glrt_eval.REPORT
METHOD = ordinary_glrt_eval.METHOD
CONTROL = "ordinary_glrt_band_capture_control"
CASES = iq_joint_trial.CASES
BOUNDARY = "Held ordinary fine-band IQ factor substitution plus complete ordinary archive"


def position(case, work, cpu):
    with (
        patch.multiple(
            ordinary_front_position,
            REPORT=REPORT,
            METHOD=METHOD,
            CONTROL=CONTROL,
            BOUNDARY=BOUNDARY,
            ordinary_front_eval=ordinary_glrt_eval,
        ),
        patch.object(iq_stream, "MAX_CHUNK_PREFIX", ordinary_glrt_eval.CHUNK_PREFIX),
    ):
        ordinary_front_position.position(case, work, cpu)


def _positive_plant(control):
    return (
        all(
            any(abs(c[1] - 735) <= 2 and abs(c[2] - 48000) < 1000 for c in rx)
            for rx in control["positives"]["control"]
        )
        and len(control["positives"]["control"]) == 2
    )


def _summary(arch, work):
    receipts = [
        json.loads(gzip.decompress((REPORT / f"{c}-{arch}.json.gz").read_bytes())) for c in CASES
    ]
    rows = [row for receipt in receipts for row in receipt["rows"]]
    valid = [row for row in rows if row["status"] == "processed"]
    controls = [receipt["controls"] for receipt in receipts]
    stock_path = NATIVE_LIBRARY if arch == "host" else ARM_CONTROL / "leo-native-glrt-short-window"
    binaries = {"control": stock_path, METHOD: work / arch / stock_path.name}
    timing = {}
    for mode in ordinary_glrt_eval.MODES:
        all_reps = [repeat for row in valid for repeat in row["timings"][mode]]
        warm_reps = (
            all_reps
            if arch == "arm"
            else [
                repeat
                for receipt in receipts
                for index, row in enumerate(
                    r for r in receipt["rows"] if r["status"] == "processed"
                )
                for repeat in row["timings"][mode][int(index == 0) :]
            ]
        )
        cold = {}
        for receipt in receipts:
            first = next(r for r in receipt["rows"] if r["status"] == "processed")
            cold[receipt["case"]] = dict(
                context_construction=receipt["host_context_construction"].get(mode),
                first_call=first["timings"][mode][0],
            )
        cpu = [r["detector_cpu_ms"] for r in warm_reps]
        wall = [r["wall_s"] * 1000 for r in warm_reps]
        timing[mode] = dict(
            cold=cold,
            repeat_count=len(warm_reps),
            detector_cpu_ms=sum(cpu),
            median_cpu_ms=median(cpu),
            max_cpu_ms=max(cpu),
            median_wall_ms=median(wall),
            max_wall_ms=max(wall),
            cpu_deadline_count=sum(v <= 20 for v in cpu),
            wall_deadline_count=sum(v <= 20 for v in wall),
            fine_fft_cpu_ms=sum(t["fine_fft"] for r in warm_reps for t in r["rows"]),
            emitted_positives=sum(len(rx) for row in valid for rx in row["positives"][mode]),
            emulator_peak_kib=max((rep.get("emu_peak_kib", 0) for rep in all_reps), default=0),
            executable_bytes=binaries[mode].stat().st_size,
            binary_sha256=_sha(binaries[mode]),
        )
    fine = timing["control"]["fine_fft_cpu_ms"]
    original = timing["control"]["detector_cpu_ms"]
    return dict(
        measured_actual=len(valid),
        scheduled=len(rows),
        exact_payloads=sum(row["exact"] for row in valid),
        exact_controls=sum(r["exact"] for table in controls for r in table.values()),
        planted_weak_positive_controls=sum(_positive_plant(table["faint"]) for table in controls),
        original_negative_controls=sum(
            not any(table[name]["positives"]["control"])
            for table in controls
            for name in ("empty", "noise")
        ),
        mode_timing=timing,
        no_fine_fft_speedup_bound=original / (original - fine),
        paired_harness_peak_kib={r["case"]: r["paired_resident_peak_kib"] for r in receipts},
        pooled_cpu_reduction=1 - timing[METHOD]["detector_cpu_ms"] / original,
        pooled_fine_cpu_reduction=1 - timing[METHOD]["fine_fft_cpu_ms"] / fine,
    )


def package(work):
    summary = {arch: _summary(arch, work) for arch in ("host", "arm")}
    host = summary["host"]
    save_json(
        REPORT / "qualification.json",
        dict(
            summary=summary,
            adoption=(
                host["pooled_cpu_reduction"] >= 0.05
                and host["exact_payloads"] == host["measured_actual"]
                and host["exact_controls"] == 6
                and host["planted_weak_positive_controls"] == 2
            ),
        ),
    )
    receipts = {case: iq_joint_trial.read(work / f"{case}-position.json") for case in CASES}
    for field, name in (("trial", "positions.jsonl.gz"), ("stock", "control-positions.jsonl.gz")):
        rows = b"".join(encoded(r[field]) + b"\n" for r in receipts.values())
        write(REPORT / name, gzip.compress(rows, mtime=0))
    save_json(REPORT / "position-receipts.json", receipts)
    names = (
        "PROTOCOL.md",
        "source-lock.json",
        "qualification.json",
        "position-receipts.json",
        "positions.jsonl.gz",
        "control-positions.jsonl.gz",
        "figures.json",
        *(f"{c}-{arch}.json.gz" for c in CASES for arch in ("host", "arm")),
        *(f"{c}-{arch}-profile.json" for c in CASES for arch in ("host", "arm")),
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(CASES),
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", required=True, type=Path)
    cli.add_argument("--case", choices=CASES)
    cli.add_argument("--cpu", type=int)
    args = cli.parse_args()
    work = local_output(args.work)
    if args.case is None:
        package(work)
    else:
        position(args.case, work, args.cpu)
