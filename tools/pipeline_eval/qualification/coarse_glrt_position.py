"""Seal exact regional bank evidence and fit its held native factors."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from statistics import median
from unittest.mock import patch

from ..__main__ import encoded, local_output, save_json, write
from ..variants import iq_stream
from . import (
    coarse_glrt_eval,
    iq_joint_trial,
    ordinary_front_build,
    ordinary_front_position,
    ordinary_glrt_profile,
)
from .full_v5_check import NATIVE_LIBRARY, _sha

REPORT = coarse_glrt_eval.REPORT
METHOD = coarse_glrt_eval.METHOD
CONTROL = "coarse_glrt_triplet_capture_control"
CASES = iq_joint_trial.CASES
BOUNDARY = "Held ordinary regional triplet IQ factors plus complete ordinary archive"


def position(case, work, cpu):
    with (
        patch.multiple(
            ordinary_front_position,
            REPORT=REPORT,
            METHOD=METHOD,
            CONTROL=CONTROL,
            BOUNDARY=BOUNDARY,
            ordinary_front_eval=coarse_glrt_eval,
        ),
        patch.object(iq_stream, "MAX_CHUNK_PREFIX", coarse_glrt_eval.CHUNK_PREFIX),
    ):
        ordinary_front_position.position(case, work, cpu)


def profile(case, work):
    src = ordinary_glrt_profile.C_SOURCE.read_text()
    replace = ordinary_front_build.replace
    src = replace(src, "fine_fft_cpu_ms,alloc_cleanup_cpu_ms", "coarse_cpu_ms,alloc_cleanup_cpu_ms")
    src = replace(src, ".fine_fft_ms;", ".coarse_ms;")
    path = work / f"{case}-coarse-profile.c"
    path.write_text(src)
    with patch.multiple(ordinary_glrt_profile, C_SOURCE=path, ordinary_glrt_eval=coarse_glrt_eval):
        for arch in ("host", "arm"):
            ordinary_glrt_profile.run(case, arch, work)


def controls(receipts):
    planted = dict(
        faint=(735, 48000), subthreshold_plant=(1173, -197125), cw_and_real_pilot=(997, -114250)
    )
    return {
        r["case"]: {
            name: dict(
                equal=row["exact"],
                positives=[len(rx) for rx in row["positives"]["control"]],
                matches=[
                    [
                        dict(epoch=c[1], cfo_hz=c[2], margin=c[3])
                        for c in rx
                        if abs(c[1] - planted[name][0]) <= 2 and abs(c[2] - planted[name][1]) < 1000
                    ]
                    for rx in row["positives"]["control"]
                ]
                if name in planted
                else None,
            )
            for name, row in r["controls"].items()
        }
        for r in receipts
    }


def summarize(arch, work):
    receipts = [
        json.loads(gzip.decompress((REPORT / f"{c}-{arch}.json.gz").read_bytes())) for c in CASES
    ]
    rows = [row for r in receipts for row in r["rows"]]
    valid = [r for r in rows if r["status"] == "processed"]
    original = (
        NATIVE_LIBRARY
        if arch == "host"
        else ordinary_front_build.ARM_CONTROL / "leo-native-glrt-short-window"
    )
    binaries = {"control": original, METHOD: work / arch / original.name}
    timing = {}
    for mode in coarse_glrt_eval.MODES:
        repetitions = [
            call
            for receipt in receipts
            for i, row in enumerate(row for row in receipt["rows"] if row["status"] == "processed")
            for call in row["timings"][mode][int(i == 0 and arch == "host") :]
        ]
        cpu = [r["detector_cpu_ms"] for r in repetitions]
        wall = [1000 * r["wall_s"] for r in repetitions]
        stages = Counter()
        for r in repetitions:
            for receiver in r["rows"]:
                stages.update(receiver)
        timing[mode] = dict(
            n=len(cpu),
            cpu_ms=sum(cpu),
            median_cpu_ms=median(cpu),
            max_cpu_ms=max(cpu),
            median_wall_ms=median(wall),
            max_wall_ms=max(wall),
            cpu_deadline=sum(t <= 20 for t in cpu),
            wall_deadline=sum(t <= 20 for t in wall),
            stages_ms=dict(stages),
            emulator_peak_kib=max((r.get("emu_peak_kib", 0) for r in repetitions), default=0),
            emitted_positives=sum(len(rx) for r in valid for rx in r["positives"][mode]),
            executable_bytes=binaries[mode].stat().st_size,
            binary_sha256=_sha(binaries[mode]),
        )
    stock, new = timing["control"], timing[METHOD]
    coarse = stock["stages_ms"]["coarse"]
    total = stock["cpu_ms"]
    return dict(
        timing=timing,
        scheduled=len(rows),
        processed=len(valid),
        exact=sum(r["exact"] for r in valid),
        controls=controls(receipts),
        host_pair_rss_kib={r["case"]: r["paired_resident_peak_kib"] for r in receipts},
        whole_cpu_reduction=1 - new["cpu_ms"] / total,
        regional_bank_reduction=1 - new["stages_ms"]["coarse"] / coarse,
        zero_coarse_speedup_bound=total / (total - coarse),
    )


def package(work):
    summary = {arch: summarize(arch, work) for arch in ("host", "arm")}
    host = summary["host"]
    adoption = (
        host["whole_cpu_reduction"] >= 0.03
        and host["exact"] == host["processed"]
        and all(r["equal"] for c in host["controls"].values() for r in c.values())
    )
    save_json(REPORT / "qualification.json", dict(summary=summary, adoption=adoption))
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
        *(
            f"{c}-{a}{ending}"
            for c in CASES
            for a in ("host", "arm")
            for ending in (".json.gz", "-profile.json")
        ),
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
        profile(args.case, work)
