"""Summarize the sealed CFO-stride candidate, RF controls and native cell audit."""

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, encoded, save_json, write
from . import scout_stride_build, scout_stride_diagnostics, scout_stride_eval
from .full_v5_check import PRODUCERS, _sha
from .scout_budget_results import unpack

REPORT = scout_stride_eval.REPORT
MODES = scout_stride_eval.MODES


def summary(trials):
    admitted = [r for t in trials for r in t["rows"] if r["status"] == "processed"]
    data, identities = {}, {}
    for mode in MODES:
        timing = [
            x
            for t in trials
            for i, r in enumerate(v for v in t["rows"] if v["status"] == "processed")
            for x in r["timings"][mode][int(i == 0) :]
        ]
        cpu, wall = [x["detector_cpu_ms"] for x in timing], [x["wall_s"] * 1000 for x in timing]
        stages = Counter()
        for x in timing:
            for r in x["rows"]:
                stages.update(r)
        receivers = [(t["id"], r) for t in trials for r in t["archive"]["receivers"]]
        fits = [r["native_fit"][mode] for _, r in receivers]
        identities[mode] = {
            (case, r["visit"], r["receiver"], m["production_rank"])
            for case, r in receivers
            for m in r["native_fit"][mode]["positive_matches"]
        }
        data[mode] = dict(
            calls=len(timing),
            pooled_cpu_ms=sum(cpu),
            median_cpu_ms=median(cpu),
            max_cpu_ms=max(cpu),
            median_wall_ms=median(wall),
            max_wall_ms=max(wall),
            cpu_by_20ms=sum(x <= 20 for x in cpu),
            wall_by_20ms=sum(x <= 20 for x in wall),
            stages_cpu_ms=dict(stages),
            archive_positives=sum(r["archive_positive_count"] for _, r in receivers),
            native_positives=sum(r["native_positive"] for r in fits),
            final_matches=len(identities[mode]),
            raw_cfo_matches=sum(
                abs(x["raw_cfo_delta_hz"]) < 1000 for r in fits for x in r["positive_matches"]
            ),
            candidate_records=sum(
                rr["candidate_count"] for r in admitted for rr in r["payloads"][mode]["rows"]
            ),
        )
    return dict(
        scheduled=sum(len(t["rows"]) for t in trials),
        admitted=len(admitted),
        changed_full_slates=sum(not r["exact"] for r in admitted),
        modes=data,
        gained_archive_ranks=sorted(identities["stride"] - identities["control"]),
        lost_archive_ranks=sorted(identities["control"] - identities["stride"]),
    )


def publish(work):
    if scout_stride_eval.sources() != json.loads((REPORT / "source-lock.json").read_bytes()):
        raise ValueError("Acquisition measurement source changed")
    trials = [unpack(REPORT / f"{case}-held.json.gz") for case in PRODUCERS]
    for trial in trials:
        native = gzip.compress(encoded(trial["rows"]), mtime=0)
        if hashlib.sha256(native).hexdigest() != trial["fresh_receipt_sha256"]:
            raise ValueError("Compared paired payloads differ from the pre-archive receipt")
    grid = unpack(REPORT / "grid-traces.json.gz")
    if _sha(Path(scout_stride_diagnostics.__file__)) != grid["diagnostic_program_sha256"]:
        raise ValueError("Grid trace source changed")
    smoke = unpack(REPORT / "smoke.json.gz")
    plants = {
        name: {
            m: [
                [
                    sum(abs(v[1] - e) <= 2 and abs(v[2] - f) < 1000 for v in rx)
                    for rx in row["positives"][m]
                ]
                for e, f, _ in row["planted"]
            ]
            for m in MODES
        }
        for name, row in smoke["results"].items()
    }
    save_json(
        REPORT / "qualification.json",
        dict(
            held=summary(trials),
            independent_cases={t["id"]: summary([t]) for t in trials},
            actual_coarse_cells=[
                dict(id=r["id"], visit=r["visit"], receivers=r["receivers"]) for r in grid["rows"]
            ],
            matched_smoke=plants,
        ),
    )
    save_json(REPORT / "release.json", scout_stride_eval.release(work))
    for mode in MODES:
        write(REPORT / f"{mode}-build.json", (work / mode / "build-receipt.json").read_bytes())
    tests = [
        ROOT / "tests/pipeline_eval" / name
        for name in ("test_scout_stride.py", "test_scout_stride_coarse.c")
    ]
    save_json(REPORT / "test-lock.json", {p.name: _sha(p) for p in tests})
    names = (
        "source-lock.json",
        "test-lock.json",
        "compatibility.json",
        "PROTOCOL.md",
        "release.json",
        "control-build.json",
        "stride-build.json",
        "qualification.json",
        "grid-traces.json.gz",
        "smoke.json.gz",
        *(f"{c}-{split}.json.gz" for c in PRODUCERS for split in ("dev", "held")),
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(PRODUCERS),
            files={n: _sha(REPORT / n) for n in names},
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=scout_stride_build.ROOT)
    publish(p.parse_args().work)
