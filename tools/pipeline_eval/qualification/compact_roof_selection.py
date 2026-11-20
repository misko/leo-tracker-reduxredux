"""Bounded five-round compact secant replay on the frozen DS26 complement."""

import argparse
import fcntl
import os
from pathlib import Path
from time import monotonic, time

from .. import corpus
from ..__main__ import local_output, run_one, save_json
from ..scoring import ARMS, validate_result
from . import projector_roof
from . import secant_confirmation as secant
from .full_v5_check import _sha

REPORT = corpus.REPO / "reports/2026_11_19_receiver_screening/redesign/roof-selection/compact"
METHOD = secant.METHOD
HASH_PREFIX = "roof-selection-v1:"
CAP = 195
WALL = 12 * 60
RESERVE = 5


def roster():
    full, files = corpus._selection("ds26-all159")
    common, common_files = corpus._selection("ds26-common127")
    if (
        len(set(full)) != 159
        or len(set(common)) != 127
        or not set(common) <= set(full)
        or files != common_files
    ):
        raise ValueError("the two frozen DS26 roof panels changed")
    canonical = sorted(set(full) - set(common))
    order = sorted(canonical, key=lambda ident: corpus._sha((HASH_PREFIX + ident).encode("ascii")))
    return canonical, order, files


def prepare(work, output):
    work.mkdir(parents=True, exist_ok=False)
    (work / "claims").mkdir()
    (work / "runs").mkdir()
    canonical, order, files = roster()
    items = corpus._index(corpus._read_frozen("inputs.jsonl", files))
    sources = secant.frozen_sources()
    cases, bindings = {}, {}
    for ident in canonical:
        item = items[ident]
        case = corpus._public(item, corpus.DEFAULT_BULK, corpus.DEFAULT_BLIND, work / "inputs")
        cases[ident] = case
        eligible = all(case[k] for k in ("native_path", "catalog_path", "request_path"))
        native, catalogue, request = (
            item.get(k, {}).get("sha256") for k in ("native", "catalog", "request")
        )
        bindings[ident] = dict(
            id=ident,
            eligible=eligible,
            frozen_unavailable=item.get("unavailable"),
            native_sha256=native,
            catalog_sha256=catalogue,
            frozen_request_sha256=request,
            prepared_request_sha256=_sha(Path(case["request_path"])) if eligible else None,
            input_sha256=projector_roof.input_hash(case) if eligible else None,
            tile=item["regions"][0],
            input_issues=case["input_issues"],
        )
    plan = dict(
        cases=canonical,
        order=order,
        hash_prefix=HASH_PREFIX,
        worker_cap_s=CAP,
        wall_cap_s=WALL,
        bindings=bindings,
        compact_sources=sources,
        cli_digest=secant._cli_digest(),
        frozen_panels_sha256=files["panels.json"],
        frozen_inputs_sha256=files["inputs.jsonl"],
    )
    save_json(work / "cases.json", cases)
    save_json(work / "plan.json", plan)
    save_json(output / "roster.json", plan)
    save_json(work / "clock.json", dict(started_monotonic_s=monotonic(), started_unix_s=time()))
    eligible_count = sum(b["eligible"] for b in bindings.values())
    print(f"Frozen {len(canonical)} scheduled, {eligible_count} eligible", flush=True)


def claim(work, plan, cpu, deadline):
    if monotonic() + CAP + RESERVE > deadline:
        return None
    with (work / "queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if monotonic() + CAP + RESERVE > deadline:
            return None
        for ident in plan["order"]:
            path = work / "claims" / f"{ident}.json"
            if plan["bindings"][ident]["eligible"] and not path.exists():
                save_json(path, dict(id=ident, cpu=cpu, claimed_monotonic_s=monotonic(), cap_s=CAP))
                return ident
    return None


def audit_result(row, plan):
    binding = plan["bindings"][row["id"]]
    for key in ("input_sha256", "native_sha256", "catalog_sha256", "frozen_request_sha256", "tile"):
        if row[key] != binding[key]:
            raise ValueError(f"{row['id']} worker uses a different frozen input")
    result = row["result"]
    validate_result(result)
    if result["status"] == "ok":
        params = result["metrics"]
        if (
            row["implementation_sha256"] != plan["cli_digest"]
            or params["kernel_sha256"] != plan["compact_sources"]["orbit_projector.c"]
            or not params["initial_phase_refresh_counts"]
            or any(n != 5 for n in params["initial_phase_refresh_counts"])
            or set(result["arms"]) != set(ARMS)
        ):
            raise ValueError("candidate changed the locked compact secant solver or refresh budget")


def lane(work, cpu):
    plan = secant.phase._read(work / "plan.json")
    cases = secant.phase._read(work / "cases.json")
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10:
        raise ValueError("use one granted CPU at nice +10 or lower priority")
    if (
        secant.frozen_sources() != plan["compact_sources"]
        or secant._cli_digest() != plan["cli_digest"]
    ):
        raise ValueError("worker differs from the source locked before scheduling")
    deadline = secant.phase._read(work / "clock.json")["started_monotonic_s"] + WALL
    while (ident := claim(work, plan, cpu, deadline)) is not None:
        binding = plan["bindings"][ident]
        row = run_one(METHOD, cases[ident], work, CAP, cpu)
        result = row["result"]
        result.setdefault("arms", {arm: dict(latlon=None) for arm in ARMS})
        row.update(
            {
                key: binding[key]
                for key in ("native_sha256", "catalog_sha256", "frozen_request_sha256", "tile")
            },
            method=METHOD,
            mode="matched-tile",
            attempted=True,
            cpu=cpu,
            deadline_s=CAP,
            source="fresh_complement_replay",
            worker_returned=row.get("implementation_sha256") is not None,
        )
        audit_result(row, plan)
        save_json(work / "runs" / f"{ident}.json", row)
        print(ident, cpu, result["status"], round(row["worker_wall_s"], 2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "lane"))
    parser.add_argument("--work", type=local_output, required=True)
    parser.add_argument("--out", type=local_output, default=REPORT)
    parser.add_argument("--cpu", type=int)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.work, args.out)
    elif args.cpu is None:
        parser.error("lane needs a single granted CPU")
    else:
        lane(args.work, args.cpu)


if __name__ == "__main__":
    main()
