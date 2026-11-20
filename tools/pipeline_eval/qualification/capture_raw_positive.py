"""Check two positive prefix visits separately from the fixed held roster."""

import argparse
import gzip
import json
import os
from pathlib import Path

from ..__main__ import encoded, local_output, write
from . import capture_raw_boundary as trial
from .full_v5_check import PRODUCERS, _bind_producer, _load_case, _sha
from .pilot_kernel_eval import _windows

CASE = "DS29-0082"


def positive_visits(rows):
    return [
        r
        for r in rows
        if r["policy_status"] == "processed"
        and any(p["candidates"] for p in trial.positives(r["production"]))
    ][:2]


def run(work, out):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner import fast_scan_analysis as analysis
    from leo.scanner import fast_scan_detector as detector

    if os.sched_getaffinity(0) != {trial.PINS[CASE]} or os.nice(0) < 10:
        raise ValueError("priority or affinity differs from the held DS29 setup")
    source = work / "source-lock.json"
    if json.loads(source.read_bytes())["files"] != trial.sources():
        raise ValueError("accelerated comparison source changed")
    prefixes = work / (CASE + "-prefix") / "visits.jsonl"
    rows = positive_visits(map(json.loads, prefixes.read_text().splitlines()))
    if len(rows) != 2:
        raise ValueError("the fixed prefix must provide two positive coverage visits")
    case, policy = _load_case(CASE), FastScanPolicyV2()
    _bind_producer(case, PRODUCERS[CASE], policy)
    out.mkdir(exist_ok=False)
    result = []
    with trial.faster(out) as configured:
        for w, archived in zip(_windows(case, 0, [r["visit"] for r in rows]), rows, strict=True):
            if (
                w.iq_sha256 != archived["iq_sha256"]
                or w.acquisition["global_visit"] != archived["visit"]
            ):
                raise ValueError("positive-coverage IQ differs from the measured prefix")
            with configured():
                answer, timing = trial.witness(analysis, detector, w, policy, "production")
            if answer.status != "processed":
                raise ValueError("accelerated capture path left the actual valid prefix")
            factors = trial.as_probes(w, answer)
            result.append(
                dict(
                    corpus_visit=archived["visit"],
                    iq_sha256=w.iq_sha256,
                    exact_positive_payload=trial.positives(factors)
                    == trial.positives(archived["production"]),
                    original_count=sum(
                        len(r["candidates"]) for r in trial.positives(archived["production"])
                    ),
                    accelerated_count=sum(len(r["candidates"]) for r in trial.positives(factors)),
                    accelerated=timing,
                    accelerated_probes=factors,
                )
            )
    value = dict(
        case=CASE,
        selection="First two authentic prefix visits with positive factors",
        prefix_sha256=_sha(prefixes),
        source_lock_sha256=_sha(source),
        driver_sha256=_sha(Path(__file__)),
        rows=result,
    )
    write(out / "positive-prefix.json.gz", gzip.compress(encoded(value), mtime=0))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.work, local_output(a.output))
