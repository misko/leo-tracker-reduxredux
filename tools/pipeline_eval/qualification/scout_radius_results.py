"""Seal the radius-only operating point, paired archived matches and coarse traces."""

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, encoded, save_json, write
from . import scout_radius_build, scout_radius_compat, scout_radius_eval, scout_radius_trace
from .full_v5_check import PRODUCERS, _sha
from .scout_budget_results import unpack

REPORT = scout_radius_eval.REPORT
MODES = scout_radius_eval.MODES


def rank_outcome(trace):
    peaks = sorted(trace["peaks"], key=lambda p: (-float.fromhex(p[2]), abs(p[1]), p[0]))
    selected, outcomes = [], {}
    for epoch, cfo, score, gate in peaks:
        entry = [epoch, cfo, score, gate]
        if len(selected) == 8:
            cause = "rank-cap"
        elif any(
            min(abs(epoch - p[0]), 13333 - abs(epoch - p[0])) < 5 and abs(cfo - p[1]) <= 10_000
            for p in selected
        ):
            cause = "suppressed"
        else:
            cause = "kept" if gate == "1" else "kept-but-gated"
            selected.append(entry)
        outcomes.setdefault(epoch, []).append(dict(cfo_hz=cfo, score_hex=score, outcome=cause))
    if selected != trace["kept"]:
        raise ValueError("Trace rank explanation does not reproduce native selection")
    return outcomes


def summarize(sweeps):
    valid = [r for s in sweeps for r in s["rows"] if r["status"] == "processed"]
    receivers = [(s["id"], r) for s in sweeps for r in s["archive"]["receivers"]]
    entries = [
        (case, r["visit"], r["receiver"], c)
        for case, r in receivers
        for c in r["archived_positives"]
    ]
    by_mode = {}
    for mode in MODES:
        timings = [
            r
            for s in sweeps
            for i, v in enumerate(x for x in s["rows"] if x["status"] == "processed")
            for r in v["timings"][mode][int(i == 0) :]
        ]
        cpu = [r["detector_cpu_ms"] for r in timings]
        wall = [r["wall_s"] * 1000 for r in timings]
        stages = Counter()
        for t in timings:
            for row in t["rows"]:
                stages.update(row)
        top = [
            min(r["archived_positives"], key=lambda x: x["archived"]["candidate_rank"])
            for _, r in receivers
            if r["archived_positives"]
        ]
        by_mode[mode] = dict(
            calls=len(cpu),
            pooled_cpu_ms=sum(cpu),
            median_cpu_ms=median(cpu),
            max_cpu_ms=max(cpu),
            median_wall_ms=median(wall),
            max_wall_ms=max(wall),
            cpu_within_20ms=sum(t <= 20 for t in cpu),
            wall_within_20ms=sum(t <= 20 for t in wall),
            stage_cpu_ms=dict(stages),
            actual_support_counts=dict(Counter(len(r["support"][mode]) for _, r in receivers)),
            archive_eligible=sum(c["eligibility"][mode] for *_, c in entries),
            archive_top_eligible=sum(c["eligibility"][mode] for c in top),
            archive_top_records=len(top),
            archive_final_matched=sum(bool(c["final_matches"][mode]) for *_, c in entries),
            archive_raw_cfo_matches=sum(
                abs(m["raw_cfo_delta_hz"]) < 1000
                for *_, c in entries
                for m in c["final_matches"][mode]
            ),
            native_positive=sum(r["fits"][mode]["native_positive"] for _, r in receivers),
        )
    return dict(
        scheduled=sum(len(s["rows"]) for s in sweeps),
        processed=len(valid),
        changed_visits=sum(not r["exact"] for r in valid),
        archive_records=len(entries),
        modes=by_mode,
        newly_eligible=[
            p
            for p in entries
            if not p[-1]["eligibility"]["control"] and p[-1]["eligibility"]["radius2"]
        ],
        baseline_misses=[p for p in entries if not p[-1]["final_matches"]["control"]],
        newly_missing=[
            p
            for p in entries
            if p[-1]["final_matches"]["control"] and not p[-1]["final_matches"]["radius2"]
        ],
    )


def publish(work):
    if scout_radius_eval.sources() != json.loads((REPORT / "source-lock.json").read_bytes()):
        raise ValueError("Radius science source binding differs")
    rows = [unpack(REPORT / f"{case}-held.json.gz") for case in PRODUCERS]
    for r in rows:
        fresh = gzip.compress(encoded(r["rows"]), mtime=0)
        if hashlib.sha256(fresh).hexdigest() != r["fresh_receipt_sha256"]:
            raise ValueError("Reconstituted native payload differs from its before-archive receipt")
    targets = {"DS26-0036": 5275, "DS29-0082": 12464}
    traced = json.loads((REPORT / "coarse-traces.json").read_bytes())
    if _sha(Path(scout_radius_trace.__file__)) != traced["trace_source_sha256"]:
        raise ValueError("Trace implementation and measured source differ")
    explained = {
        case: {m: rank_outcome(b["trace"][1]).get(targets[case], []) for m, b in modes.items()}
        for case, modes in traced["results"].items()
    }
    summary = summarize(rows)
    smoke = unpack(REPORT / "smoke.json.gz")
    plants = {
        name: {
            mode: [
                [
                    sum(abs(x[1] - e) <= 2 and abs(x[2] - f) < 1000 for x in rx)
                    for rx in row["positives"][mode]
                ]
                for e, f, _ in row["planted"]
            ]
            for mode in MODES
        }
        for name, row in smoke["results"].items()
    }
    save_json(
        REPORT / "qualification.json",
        dict(
            held=summary,
            cases={r["id"]: summarize([r]) for r in rows},
            prespecified_trace_outcomes=explained,
            smoke_plant_matches=plants,
        ),
    )
    save_json(REPORT / "release.json", scout_radius_eval.release(work))
    for mode in MODES:
        write(REPORT / f"{mode}-build.json", (work / mode / "build-receipt.json").read_bytes())
    tests = (ROOT / "tests/pipeline_eval/test_scout_radius.py", Path(scout_radius_compat.__file__))
    save_json(REPORT / "test-lock.json", {p.name: _sha(p) for p in tests})
    names = (
        "PROTOCOL.md",
        "release.json",
        "source-lock.json",
        "test-lock.json",
        "coarse-traces.json",
        "compatibility.json",
        "control-build.json",
        "radius2-build.json",
        "qualification.json",
        "smoke.json.gz",
        *(f"{case}-held.json.gz" for case in PRODUCERS),
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
    p.add_argument("--work", type=Path, default=scout_radius_build.ROOT)
    publish(p.parse_args().work)
