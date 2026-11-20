"""Run the unchanged held-component bridge on a fixed independent roof reserve."""

import argparse
import os
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import perf_counter, time_ns
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..scoring import ARMS, validate_result
from ..variants import bridge_support, v5_lean
from . import bridge_support_eval as prior
from . import full_receiver_comparison as common
from .bridge_cavity_eval import _case, execution_binding, frozen_inputs
from .secant_end_to_end_worker import cpu_s, stamp
from .short_receiver_figures import _frozen_roof

REPORT = common.SCREEN / "redesign/bridge-reserve"
CANDIDATE, STOCK = bridge_support.METHOD, common.COMPACT
SALT = "bridge-support-reserve-v1:"
EXCLUDED = {*prior.CASES, *prior.previous.CASES, *prior.previous.DIAGNOSTIC}
CPUS = (20, 21, 22, 23)
TOTAL_S = 720
CASE_S = 145
NICE = 10
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile", "resolved_request_sha256")


def select(ids):
    eligible = set(ids) - EXCLUDED
    ranked = sorted(eligible, key=lambda i: sha256((SALT + i).encode()).digest())
    old = [i for i in ranked if i.startswith("DS26-")][:21]
    other = [i for i in ranked if i.startswith("DS29-")]
    if len(old) != 21 or len(other) != 3:
        raise ValueError("expected 21 selected DS26 and all three remaining DS29")
    return old + other


def source():
    sealed = common.read(prior.REPORT / "source-lock.json")
    if sealed["source"] != prior.sources():
        raise ValueError("the live bridge differs from its sealed recovery experiment")
    files = (
        Path(__file__),
        REPORT / "PROTOCOL.md",
        prior.REPORT / "receipt.json",
        prior.REPORT / "source-lock.json",
    )
    return {
        **sealed["source"],
        **{str(p.relative_to(common.ROOT)): common.sha(p) for p in files},
    }


def controls():
    refs, inventory = _frozen_roof()
    inputs = common.full_roster(refs, inventory)
    records, ledger = common.compact_predictions(inputs, refs, audit_archive=True)
    return records, ledger


def lock(path):
    inputs = frozen_inputs()
    cases = select(inputs)
    bindings = {i: execution_binding(inputs[i], _case(inputs[i])) for i in cases}
    stock, ledger = controls()
    for ident, bound in bindings.items():
        common.require_fields(stock[ident], {k: bound[k] for k in MATCH})
    path = local_output(path)
    if path.exists():
        raise FileExistsError(path)
    # Interleave the three retained DS29 cases across the first lanes.
    order = [*cases[-3:], *cases[:-3]]
    lanes = {str(cpu): order[k :: len(CPUS)] for k, cpu in enumerate(CPUS)}
    save_json(
        path,
        dict(
            cases=cases,
            bindings=bindings,
            excluded=sorted(EXCLUDED),
            salt=SALT,
            source=source(),
            compact_ledger=ledger,
            lanes=lanes,
            nice=NICE,
            limit_s=CASE_S,
            total_s=TOTAL_S,
            locked_ns=time_ns(),
        ),
    )


def native_counts(work):
    result = Counter()
    hashes = {}
    for receipt in sorted((work / "receipts" / "native").glob("*.json")):
        payload = common.read(receipt)
        result.update(payload["counts"])
        hashes[receipt.name] = common.sha(receipt)
    return dict(result), hashes


def unavailable(status, reason):
    return dict(
        status=status,
        reason=reason,
        boundary=bridge_support.BOUNDARY,
        metrics={},
        arms={a: {"latlon": None} for a in ARMS},
    )


def replay_lane(cpu, plan_path, output):
    plan = common.read(plan_path)
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < plan["nice"]:
        raise ValueError("runner does not use the locked affinity and priority")
    if plan["source"] != source():
        raise ValueError("locked runner source changed")
    inputs = frozen_inputs()
    output = local_output(output)
    for ident in plan["lanes"][str(cpu)]:
        case = _case(inputs[ident])
        binding = execution_binding(inputs[ident], case)
        if plan["bindings"][ident] != binding:
            raise ValueError(f"{ident} input differs from the locked roster")
        work = output / ident
        work.mkdir(parents=True, exist_ok=False)
        cap = min(CASE_S, (plan["locked_ns"] + TOTAL_S * 10**9 - time_ns()) // 10**9)
        start, cpu_start = perf_counter(), cpu_s()
        if cap <= 5:
            result = unavailable("missing", "not started before the shared worker deadline")
        else:
            with patch.object(v5_lean, "TIMEOUT_S", cap - 5):
                result = bridge_support.run(case, work)
            if "exceeded its " in result.get("reason", ""):
                result["status"] = "timed_out"
            elif result["status"] == "unavailable":
                log = work / "worker.log"
                if log.is_file() and b"Traceback" in log.read_bytes():
                    result["status"] = "failed"
        usage = stamp(start, cpu_start)
        if result["status"] != "ok":
            result["arms"] = {arm: {"latlon": None} for arm in ARMS}
        validate_result(result)
        request = work / "request.json"
        proof = prior._request_proof(case, request) if request.is_file() else None
        if (result["status"] == "ok" and proof is None) or plan["source"] != source():
            raise ValueError(f"{ident} completed on a different source or request")
        counts, receipts = native_counts(work)
        save_json(
            work / "measurement.json",
            dict(
                binding,
                method=CANDIDATE,
                qualification="fresh",
                cpu=cpu,
                cap_s=max(0, cap),
                worker_wall_s=usage["wall_s"] if cap > 5 else None,
                worker_cpu_s=usage["cpu_s"] if cap > 5 else None,
                resources=usage if cap > 5 else {},
                source_lock_sha256=common.sha(plan_path),
                boundary_proof=proof,
                native_counts=counts,
                native_receipts_sha256=receipts,
                result=result,
            ),
        )
        print(ident, result["status"], round(usage["wall_s"], 3), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="action", required=True)
    command.add_parser("lock").add_argument("plan", type=Path)
    run = command.add_parser("lane")
    run.add_argument("cpu", type=int, choices=CPUS)
    run.add_argument("plan", type=Path)
    run.add_argument("work", type=Path)
    args = parser.parse_args()
    if args.action == "lock":
        lock(args.plan)
    else:
        replay_lane(args.cpu, args.plan, args.work)


if __name__ == "__main__":
    main()
