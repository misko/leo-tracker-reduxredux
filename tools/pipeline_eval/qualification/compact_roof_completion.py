"""Complete only the eight pre-existing unlaunched compact roof cases."""

import argparse
import gzip
import os
from pathlib import Path
from time import monotonic, time

from ..__main__ import encoded, local_output, read_predictions, run_one, save_json, write
from ..scoring import ARMS
from . import compact_roof_selection as base
from . import compact_roof_selection_results as scoring
from .full_v5_check import _sha

REPORT = base.REPORT.with_name("completion")
PINS = (0, 2, 3, 6, 8, 9, 12, 16)
WALL = 400
PREDICTIONS = "positions.jsonl.gz"
COMBINED = "all32-positions.jsonl.gz"
READ = base.secant.phase._read
IDENTITY = ("input_sha256", "native_sha256", "catalog_sha256", "frozen_request_sha256", "tile")


def unlaunched(rows, order):
    return [
        ident
        for ident in order
        if rows[ident]["attempted"] is False
        and rows[ident]["source"] == "not_launched"
        and rows[ident]["result"]["status"] == "missing"
    ]


def prior():
    path = base.REPORT / "prediction-lock.json"
    lock = READ(path)
    if any(_sha(base.REPORT / name) != digest for name, digest in lock["files"].items()):
        raise ValueError("initial budget predictions or input roster changed")
    plan = READ(base.REPORT / "roster.json")
    rows = read_predictions(base.REPORT / PREDICTIONS)
    receipt = READ(base.REPORT / "run-receipt.json")
    order = unlaunched(rows, plan["order"])
    if (
        list(rows) != lock["cases"]
        or len(rows) != 32
        or len(order) != len(PINS)
        or set(order) & receipt["claims"].keys()
        or any(not plan["bindings"][ident]["eligible"] for ident in order)
        or base.secant.frozen_sources() != plan["compact_sources"]
        or base.secant._cli_digest() != plan["cli_digest"]
        or plan["worker_cap_s"] != base.CAP
    ):
        raise ValueError("supplement must use only prior unlaunched cases and the original solver")
    return path, lock, plan, rows, order


def prepare(work, original_work, output):
    original, _, first, rows, order = prior()
    cases = READ(original_work / "cases.json")
    for ident in order:
        binding, case = first["bindings"][ident], cases[ident]
        if (
            base.projector_roof.input_hash(case) != binding["input_sha256"]
            or _sha(Path(case["request_path"])) != binding["prepared_request_sha256"]
            or any(binding[key] != rows[ident][key] for key in IDENTITY)
        ):
            raise ValueError(f"{ident} prepared original request or paired native hash changed")
    work.mkdir(parents=True, exist_ok=False)
    (work / "runs").mkdir()
    plan = dict(
        cases=sorted(order),
        order=order,
        assignments=dict(zip(order, PINS, strict=True)),
        original_prediction_lock_sha256=_sha(original),
        worker_cap_s=base.CAP,
        wall_cap_s=WALL,
        bindings={i: first["bindings"][i] for i in order},
        compact_sources=first["compact_sources"],
        cli_digest=first["cli_digest"],
    )
    save_json(work / "cases.json", {ident: cases[ident] for ident in order})
    save_json(output / "roster.json", plan)
    save_json(work / "plan.json", plan)
    save_json(work / "clock.json", dict(started_monotonic_s=monotonic(), started_unix_s=time()))


def run(work, cpu):
    plan = READ(work / "plan.json")
    original, _, _, _, order = prior()
    if (
        _sha(original) != plan["original_prediction_lock_sha256"]
        or plan["order"] != order
        or os.sched_getaffinity(0) != {cpu}
        or os.nice(0) < 10
    ):
        raise ValueError("supplement worker changed its original seal or granted affinity")
    (ident,) = (ident for ident, assigned in plan["assignments"].items() if assigned == cpu)
    path = work / "runs" / f"{ident}.json"
    if (
        path.exists()
        or monotonic() + base.CAP + base.RESERVE
        > READ(work / "clock.json")["started_monotonic_s"] + WALL
    ):
        raise ValueError("supplement requires exactly one complete slot per recording")
    case = READ(work / "cases.json")[ident]
    binding = plan["bindings"][ident]
    if (
        base.projector_roof.input_hash(case) != binding["input_sha256"]
        or _sha(Path(case["request_path"])) != binding["prepared_request_sha256"]
    ):
        raise ValueError("the completion case differs from the earlier prepared request")
    row = run_one(base.METHOD, case, work, base.CAP, cpu)
    row["result"].setdefault("arms", {arm: dict(latlon=None) for arm in ARMS})
    row.update(
        {key: binding[key] for key in IDENTITY if key != "input_sha256"},
        method=base.METHOD,
        mode="matched-tile",
        attempted=True,
        cpu=cpu,
        deadline_s=base.CAP,
        source="fresh_complement_completion",
        worker_returned=row.get("implementation_sha256") is not None,
    )
    base.audit_result(row, plan)
    save_json(path, scoring.normalize_attempt(row))
    print(ident, cpu, row["result"]["status"], round(row["worker_wall_s"], 2), flush=True)


def pack(output, name, rows):
    path = output / name
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    return _sha(path)


def publish(work, output):
    original, initial_lock, _, old, order = prior()
    plan = READ(work / "plan.json")
    if (
        plan != READ(output / "roster.json")
        or plan["cases"] != sorted(order)
        or plan["original_prediction_lock_sha256"] != _sha(original)
    ):
        raise ValueError("the add-only supplement changed its frozen roster")
    rows = {}
    for ident in plan["cases"]:
        row = READ(work / "runs" / f"{ident}.json")
        base.audit_result(row, plan)
        if (
            row["source"] != "fresh_complement_completion"
            or row["attempted"] is not True
            or row["native_sha256"] is None
            or row["cpu"] != plan["assignments"][ident]
            or row["deadline_s"] != base.CAP
            or any(row[key] != old[ident][key] for key in IDENTITY)
        ):
            raise ValueError("a new row differs from its only eligible unlaunched predecessor")
        rows[ident] = row
    receipt = dict(
        original_prediction_lock_sha256=_sha(original),
        cases=plan["cases"],
        files={
            PREDICTIONS: pack(output, PREDICTIONS, rows.values()),
            "roster.json": _sha(output / "roster.json"),
        },
    )
    save_json(output / "prediction-lock.json", receipt)
    combined = pack(
        output, COMBINED, (rows.get(ident, old[ident]) for ident in initial_lock["cases"])
    )
    save_json(
        output / "all32-prediction-lock.json",
        dict(
            cases=initial_lock["cases"],
            files={COMBINED: combined},
            original_prediction_lock_sha256=_sha(original),
            supplement_prediction_lock_sha256=_sha(output / "prediction-lock.json"),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "publish"))
    parser.add_argument("--work", type=local_output, required=True)
    parser.add_argument("--original-work", type=Path)
    parser.add_argument("--out", type=local_output, default=REPORT)
    parser.add_argument("--cpu", type=int, choices=PINS)
    args = parser.parse_args()
    if args.action == "prepare" and args.original_work is not None:
        prepare(args.work, args.original_work, args.out)
    elif args.action == "run" and args.cpu is not None:
        run(args.work, args.cpu)
    elif args.action == "publish":
        publish(args.work, args.out)
    else:
        parser.error("prepare requires original work, run requires a granted CPU")


if __name__ == "__main__":
    main()
