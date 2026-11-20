"""Qualify actual saved-IQ acquisition scheduling against the full ordinary runs."""

import argparse
import gzip
import json
from math import ceil
from pathlib import Path
from statistics import mean, median
from unittest.mock import patch

from ..__main__ import encoded, local_output, references, save_json, write
from ..variants import interleaved_visits
from . import iq_schedule_worker as worker
from . import raw_robust, whole_cavity_scores, whole_pair
from . import whole_memory_chain as apparatus
from .full_v5_check import _sha
from .prefix_figures import csv_file

REPORT = whole_pair.REPORT.with_name("iq-schedule")
RUNS = whole_pair.RUNS.with_name("iq-schedule")
CASES = ("DS29-0082", "DS26-0036")


def rows(path):
    return {r["id"]: r for r in map(json.loads, gzip.decompress(path.read_bytes()).splitlines())}


def control(ident):
    return rows(apparatus.sealed(whole_pair.REPORT, "positions.jsonl.gz"))[ident]


def plan():
    earlier = whole_pair.preseal()
    if earlier != json.loads((whole_pair.REPORT / "source-lock.json").read_bytes()):
        raise ValueError("the full-visit replay differs from its frozen source")
    positions = apparatus.sealed(whole_pair.REPORT, "positions.jsonl.gz")
    stages = apparatus.sealed(whole_pair.REPORT, "stages.json.gz")
    sources = (
        Path(__file__),
        Path(worker.__file__),
        Path(interleaved_visits.__file__),
        REPORT / "PROTOCOL.md",
        REPORT.with_name("interleaved-visits") / "PROTOCOL.md",
        whole_pair.REPORT / "prediction-lock.json",
        positions,
        stages,
    )
    inputs = {}
    for ident in CASES:
        capture = earlier["inputs"][ident]
        reference = raw_robust.prior_directory(ident) / "native.json"
        if (
            _sha(reference) != capture["native_sha256"]
            or control(ident)["result"]["status"] != "ok"
        ):
            raise ValueError("missing authenticated full ordinary factors and position")
        inputs[ident] = dict(capture, full_native_path=str(reference))
    return dict(
        earlier,
        inputs=inputs,
        recording_order=list(CASES),
        sources=dict(earlier["sources"]) | {str(p): _sha(p) for p in sources},
    )


def native_durations(trace):
    raw = trace["raw"]
    if raw is None:
        return {}
    visits = [v for lane in raw["raw_lanes"] for v in lane["native_timings_s"]]
    wall, cpu = map(sorted, zip(*visits, strict=True))
    return dict(
        physical_calls=len(wall),
        wall_ms=dict(
            mean=1000 * mean(wall),
            median=1000 * median(wall),
            p95=1000 * wall[ceil(0.95 * len(wall)) - 1],
        ),
        cpu_ms=dict(
            mean=1000 * mean(cpu),
            median=1000 * median(cpu),
            p95=1000 * cpu[ceil(0.95 * len(cpu)) - 1],
        ),
        wall_at_most_20ms=sum(w <= 0.020 for w in wall),
        cgroup_replay_cpu_s=(
            trace["position"]["end"]["cpu.stat.usage_usec"] - trace["start"]["cpu.stat.usage_usec"]
        )
        / 1e6
        if trace["position"]
        else None,
        span_seconds=raw["capture_seconds"],
    )


def publish(runs, report):
    pins = json.loads((runs / "plan.json").read_bytes())
    if plan() != pins:
        raise ValueError("schedule qualification source or full ordinary authority changed")
    ids = [i for i in CASES if (runs / f"{i}-service.json").is_file()]
    if not ids:
        raise ValueError("no bounded service attempt is available for publication")
    full_trace = json.loads(
        gzip.decompress(apparatus.sealed(whole_pair.REPORT, "stages.json.gz").read_bytes())
    )
    records, trace, comparators = [], {}, []
    with patch.multiple(apparatus, chain=worker, control=control):
        for ident in ids:
            new, trace[ident] = apparatus.summarize(runs, ident)
            new["origin_native_sha256"] = pins["inputs"][ident]["native_sha256"]
            if trace[ident]["raw"] is None:
                new["native_sha256"] = None
            records.append(new)
            comparators.append(control(ident))
    comparison = {}
    for ident in ids:
        wide = native_durations(full_trace[ident])
        changed = native_durations(trace[ident])
        comparison[ident] = dict(
            full=wide,
            scheduled=changed,
            fraction_of_original_calls=changed.get("physical_calls", 0) / wide["physical_calls"]
            if changed
            else None,
        )
    save_json(report / "source-lock.json", pins)
    save_json(report / "comparison.json", comparison)
    for filename, data in (
        ("positions.jsonl.gz", b"".join(encoded(x) + b"\n" for x in records)),
        ("control-positions.jsonl.gz", b"".join(encoded(x) + b"\n" for x in comparators)),
        ("stages.json.gz", encoded(trace)),
    ):
        write(report / filename, gzip.compress(data, mtime=0))
    files = (
        "positions.jsonl.gz",
        "control-positions.jsonl.gz",
        "stages.json.gz",
        "comparison.json",
    )
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=ids,
            files={name: _sha(report / name) for name in files},
            source_lock_sha256=_sha(report / "source-lock.json"),
        ),
    )
    truth = {r["id"]: r["truth"] for r in references("roof16", ids)[1]}
    scores = [
        dict(s, method=row["method"])
        for row in (*records, *comparators)
        for s in whole_cavity_scores.arm_scores(row, truth[row["id"]])
    ]
    csv_file(report / "scores.csv", scores)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "run", "publish"))
    p.add_argument("--case", choices=CASES)
    p.add_argument("--runs", type=local_output, default=RUNS)
    a = p.parse_args()
    if a.action == "seal":
        a.runs.mkdir(parents=True, exist_ok=False)
        save_json(a.runs / "plan.json", plan())
    elif a.action == "run":
        if not a.case:
            p.error("select a recording")
        with patch.multiple(apparatus, chain=worker, control=control, plan=plan):
            apparatus.run(a.case, a.runs)
    else:
        publish(a.runs, REPORT)


if __name__ == "__main__":
    main()
