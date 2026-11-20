"""Measure true position-worker time under a convergence-based phase budget."""

import argparse
import os
from pathlib import Path
from time import perf_counter, time_ns
from unittest.mock import patch

from ..__main__ import local_output, read_predictions, save_json
from ..scoring import ARMS, validate_result
from ..variants import stable_phase as candidate
from . import bridge_cavity_eval as verified
from . import secant_full
from .armijo_finish_results import pack

base = secant_full.phase
REPORT = secant_full.REPORT.parent / "recovery/stable-phase"
METHOD = candidate.METHOD
STOCK = secant_full.METHOD
LANES = (11, 19)
BOUND = 720
CASE_CAP = 230
SALT = "phase-fixed-point-v1/"


def schedule(ids):
    eligible = set(ids) - set(verified.TIMING_IDS)
    order = sorted(eligible, key=lambda k: base.corpus._sha((SALT + k).encode()))
    ds26 = [k for k in order if k.startswith("DS26-")][:3]
    ds29 = [k for k in order if k.startswith("DS29-")][:1]
    if len(ds26) != 3 or len(ds29) != 1:
        raise ValueError("missing roof confirmation inputs")
    return {
        "11": [["DS26-0036", METHOD], ["DS26-0036", STOCK], [ds26[0], METHOD], [ds26[2], METHOD]],
        "19": [["DS29-0082", STOCK], ["DS29-0082", METHOD], [ds29[0], METHOD], [ds26[1], METHOD]],
    }


def sources():
    files = [
        Path(__file__),
        Path(candidate.__file__),
        REPORT / "PROTOCOL.md",
        secant_full.REPORT / "prediction-lock.json",
    ]
    return dict(
        study={p.name: base.digest(p) for p in files},
        secant=secant_full.secant.frozen_sources(),
        frozen_science=candidate.v5_lean.SOURCE_SHA256,
        frozen_runner=candidate.v5_lean.RUNNER_SHA256,
    )


def archived():
    lock = base._read(secant_full.REPORT / "prediction-lock.json")
    secant_full._verify_files(secant_full.REPORT, lock["files"])
    return read_predictions(secant_full.REPORT / (STOCK + ".jsonl.gz"))


def plan(work):
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    inputs = base.frozen_inputs()
    jobs = schedule(inputs)
    ids = list(dict.fromkeys(i for items in jobs.values() for i, _ in items))
    old = archived()
    bindings = {i: verified.execution_binding(inputs[i], base._case(inputs[i])) for i in ids}
    for ident, binding in bindings.items():
        if any(
            old[ident][k] != binding[k]
            for k in ("input_sha256", "native_sha256", "catalog_sha256", "tile")
        ):
            raise ValueError("original secant was scored on different scientific input")
    save_json(
        REPORT / "plan.json",
        dict(cases=ids, schedule=jobs, bindings=bindings, source=sources(), locked_ns=time_ns()),
    )


def lane(work, cpu):
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError("one pinned CPU required")
    plan_path = REPORT / "plan.json"
    locked = base._read(plan_path)
    inputs = base.frozen_inputs()
    if locked["schedule"] != schedule(inputs) or sources() != locked["source"]:
        raise ValueError("stale phase-study worker sources or schedule")
    for ident, method in locked["schedule"][str(cpu)]:
        row = dict(locked["bindings"][ident])
        case = base._case(inputs[ident])
        if row != verified.execution_binding(inputs[ident], case):
            raise ValueError("scientific input changed")
        out = local_output(work) / f"{ident}-{method}"
        out.mkdir()
        remaining = BOUND - (time_ns() - locked["locked_ns"]) / 1e9
        cap = min(CASE_CAP, int(remaining) - 4)
        start, used = perf_counter(), verified.cpu_s()
        if cap < 4:
            result = dict(status="timed_out", reason="study deadline before execution", metrics={})
        else:
            with patch.object(candidate.v5_lean, "TIMEOUT_S", cap):
                result = (
                    candidate.run(case, out)
                    if method == METHOD
                    else candidate.v5_secant_fit.run(case, out, "secant")
                )
            if "exceeded its " in result.get("reason", ""):
                result["status"] = "timed_out"
        elapsed = verified.stamp(start, used)
        if result["status"] != "ok":
            result["arms"] = {a: dict(latlon=None) for a in ARMS}
        validate_result(result)
        proof = (
            verified._request_proof(case, out / "request.json")
            if (out / "request.json").exists()
            else None
        )
        if result["status"] == "ok" and (
            proof is None or proof["scientific_request_sha256"] != row["scientific_request_sha256"]
        ):
            raise ValueError("unverified input for completed phase fit")
        if locked["source"] != sources():
            raise ValueError("phase policy source changed during experiment")
        row.update(
            method=method,
            result=result,
            qualification="fresh",
            cpu=cpu,
            resources=elapsed,
            worker_wall_s=elapsed["wall_s"],
            request_proof=proof,
            plan_sha256=base.digest(plan_path),
        )
        save_json(out / "measured.json", row)
        print(ident, method, result["status"], round(elapsed["wall_s"], 2), flush=True)


def seal(work):
    plan_path = REPORT / "plan.json"
    info, controls = base._read(plan_path), archived()
    if info["source"] != sources():
        raise ValueError("convergence source mismatch")
    sets = {METHOD: {}, STOCK: {}}
    for cpu, lane_jobs in info["schedule"].items():
        for ident, method in lane_jobs:
            row = base._read(work / f"{ident}-{method}/measured.json")
            if any(row[k] != v for k, v in info["bindings"][ident].items()) or (
                row["cpu"],
                row["method"],
                row["plan_sha256"],
            ) != (int(cpu), method, base.digest(plan_path)):
                raise ValueError("record differs from the scheduled worker and inputs")
            sets[method][ident] = row
    files = {"plan.json": base.digest(plan_path)}
    for ident in info["cases"]:
        if ident not in sets[STOCK]:
            sets[STOCK][ident] = dict(controls[ident], qualification="archive")
        sets[STOCK][ident]["archive_same_result"] = sets[STOCK][ident]["result"].get(
            "arms"
        ) == controls[ident]["result"].get("arms")
    for method, data in sets.items():
        name = method + ".jsonl.gz"
        files[name] = pack(REPORT, name, [data[i] for i in info["cases"]])
    save_json(REPORT / "prediction-lock.json", dict(cases=info["cases"], files=files))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "lane", "seal"))
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--cpu", type=int, choices=LANES)
    args = parser.parse_args()
    if args.action == "lane":
        lane(args.work, args.cpu)
    elif args.action == "plan":
        plan(args.work)
    else:
        seal(args.work)
