"""Replay sealed anchor fits and compare RF errors on shared measured observations."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS
from . import anchor_receiver_trial as trial
from .fresh_scenes import _sandbox, _sha

WORKER = """
import importlib
import json
import sys
from unittest.mock import patch

from tools.pipeline_eval.qualification.anchor_receiver_rf_worker import measure

request = json.load(sys.stdin)
solver = importlib.import_module('tools.pipeline_eval.variants.' + request.pop('method'))
json.dump(measure(solver, request), sys.stdout, allow_nan=False)
"""


def shared_rows(outputs):
    """Require a unique measured key in every method before reporting paired residuals."""
    by_method = {}
    for method, sample in outputs.items():
        index, repeated = {}, set()
        for row in sample:
            key = tuple(row["key"])
            if key in index:
                repeated.add(key)
            index[key] = row
        by_method[method] = {key: value for key, value in index.items() if key not in repeated}
    common = set.intersection(*(set(r) for r in by_method.values()))
    for key in sorted(common):
        selected = {method: rows[key] for method, rows in by_method.items()}
        yield dict(
            key=key,
            same_orbit=len({x["norad"] for x in selected.values()}) == 1,
            same_lift=len({x["lift"] for x in selected.values()}) == 1,
            residuals={method: x["error"] for method, x in selected.items()},
        )


def _summary(rows):
    return {
        "points": len(rows),
        "rms_hz": {
            method: float(np.sqrt(np.mean([r["residuals"][method] ** 2 for r in rows])))
            if rows
            else None
            for method in trial.METHODS
        },
    }


def run(root, output):
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus or not set(cpus) <= trial.CPUS:
        raise ValueError("pin the diagnostic to the scheduled CPUs")
    sealed = {(r["id"], r["method"]): r["result"] for r in trial._verify(root)}
    queries = [r for r in trial._queries(root) if r["cohort"] != "omitted"]

    def lane(index):
        data = []
        for row in queries[index :: len(cpus)]:
            measurements = {}
            for method in trial.METHODS:
                cmd = _sandbox(cpus[index])
                cmd[-1] = WORKER
                answer = subprocess.run(
                    cmd,
                    input=encoded(row["packet"] | {"method": method}),
                    capture_output=True,
                    check=True,
                    timeout=trial.TIMEOUT,
                )
                result = json.loads(answer.stdout)
                observed = result["result"]
                expected = sealed[row["id"], method]
                if (
                    observed["arms"] != expected["arms"]
                    or observed["status"] != expected["status"]
                    or observed["reason"] != expected["reason"]
                ):
                    raise ValueError("the RF replay changed a sealed prediction")
                measurements[method] = result["samples"]
            for arm in ARMS:
                shared = list(
                    shared_rows({m: values.get(arm, []) for m, values in measurements.items()})
                )
                data.append((row["id"], row["cohort"], arm, shared))
        return data

    with ThreadPoolExecutor(len(cpus)) as pool:
        groups = [row for batch in pool.map(lane, range(len(cpus))) for row in batch]
    name = "matched-rf.jsonl.gz"
    write(
        output / name,
        gzip.compress(
            b"".join(
                encoded(dict(case=case, cohort=cohort, arm=arm, **row)) + b"\n"
                for case, cohort, arm, rows in groups
                for row in rows
            ),
            mtime=0,
        ),
    )
    summary = []
    for cohort in trial.COHORTS:
        for arm in ARMS:
            rows = [r for _, g, a, group in groups if (g, a) == (cohort, arm) for r in group]
            summary.append(
                dict(
                    cohort=cohort,
                    arm=arm,
                    common=_summary(rows),
                    same_owner_and_lift=_summary(
                        [r for r in rows if r["same_orbit"] and r["same_lift"]]
                    ),
                )
            )
    worker = Path(__file__).with_name("anchor_receiver_rf_worker.py")
    save_json(
        output / "matched-rf.json",
        dict(
            prediction_lock_sha256=_sha(root / "prediction-lock.json"),
            replay_sources={p.name: _sha(p) for p in (Path(__file__), worker)},
            residuals_sha256=_sha(output / name),
            groups=summary,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    opts = parser.parse_args()
    run(opts.root, opts.out)
