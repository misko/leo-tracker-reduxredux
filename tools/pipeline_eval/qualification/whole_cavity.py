"""Qualify ordinary whole-IQ DS26 through the exact lifetime-bounded cavity."""

import argparse
import gzip
import json
from pathlib import Path
from unittest.mock import patch

from ..__main__ import local_output, save_json
from . import cavity_lifetime_trial, whole_cavity_worker
from . import whole_memory_chain as base
from .full_v5_check import _sha

CASE = "DS26-0036"
REPORT = base.REPORT.with_name("whole-cavity")
RUNS = base.RUNS.with_name("whole-cavity")
PREVIOUS_PLAN, PREVIOUS_CONTROL, RAW = base.plan, base.control, base.chain
DONOR = base.REPORT.with_name("cavity-lifetime") / "plan.json"
ROW_MAJOR_FAILURE = base.REPORT / "ds26" / "prediction-lock.json"


def control(ident):
    path = base.sealed(base.PRIOR, "positions.jsonl.gz")
    return next(
        row
        for row in map(json.loads, gzip.decompress(path.read_bytes()).splitlines())
        if row["id"] == ident and row["method"] == "v5_secant_fit"
    )


def plan():
    with patch.multiple(base, chain=RAW, control=PREVIOUS_CONTROL):
        raw = PREVIOUS_PLAN()
    if raw != json.loads((base.REPORT / "source-lock.json").read_bytes()):
        raise ValueError("whole-IQ decoder and assembly chain differs from the earlier lock")
    donor = json.loads(DONOR.read_bytes())["source"]
    if donor != cavity_lifetime_trial.source():
        raise ValueError("cavity lifetime solver differs from its original lock")
    paths = (
        Path(__file__),
        Path(whole_cavity_worker.__file__),
        DONOR,
        REPORT / "PROTOCOL.md",
        ROW_MAJOR_FAILURE,
        base.sealed(base.PRIOR, "positions.jsonl.gz"),
    )
    oracle = control(CASE)
    native = raw["inputs"][CASE]
    if oracle["native_sha256"] != native["native_sha256"]:
        raise ValueError("cavity control has different ordinary inputs")
    return dict(
        raw,
        inputs={CASE: dict(native, control_method=oracle["method"])},
        runtime_max_s=whole_cavity_worker.LIMIT,
        sources=dict(raw["sources"]) | {str(path): _sha(path) for path in paths},
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("seal", "run", "publish"))
    cli.add_argument("--runs", type=local_output, default=RUNS)
    args = cli.parse_args()
    if args.action == "seal":
        args.runs.mkdir(parents=True, exist_ok=False)
        save_json(args.runs / "plan.json", plan())
        return
    with patch.multiple(base, chain=whole_cavity_worker, control=control, plan=plan):
        if args.action == "run":
            base.run(CASE, args.runs)
        else:
            base.publish(args.runs, REPORT)


if __name__ == "__main__":
    main()
