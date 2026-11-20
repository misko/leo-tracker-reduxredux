"""Seal a small disjoint challenge and optional full same-nuisance native run."""

import argparse
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ..variants import clock_offset
from . import native_clock_full as base

ROOT = base.base.native.ROOT
REPORT = ROOT / "reports/2026_11_19_receiver_screening/recovery/clock-offset"
REFINEMENT = REPORT.parent.parent / "refinement"
WORK = base.WORK.with_name("native-clock-offset-challenge")
WORKER = Path(__file__).with_name("clock_offset_worker.py")
CPUS = (0, 2, 3, 6)
SALT = "clock-offset-prospective-v1:"
_PLAN, _COMMAND, _BIND = base.prepare, base.command, base.bindings


def rank(ident):
    return sha256((SALT + ident).encode()).digest()


def _near(base_plan, jobs):
    parent = REFINEMENT / "boundary-roof" / "primary"
    phase = base.phase
    request = phase._read(parent / "requests.json")
    label_path = parent / "evaluator.json"
    if (
        phase.digest(label_path) != request["evaluator_sha256"]
        or request["clock_plan_sha256"] != phase.digest(base.REPORT / "plan.json")
    ):
        raise ValueError("the close wrong-offer archive differs from the locked native inputs")
    eligible = {
        label["id"] for label in phase._read(label_path)["labels"]
        if label["condition"] == "near-outside"
    }
    ident = min(eligible, key=rank)
    query = next(x for x in request["cases"] if x["id"] == ident)
    stock = next(q for q in base_plan["cases"] if q["id"] == query["recording"])
    packet = query["packet"]
    if {k: v for k, v in stock["packet"].items() if k != "offer"} != {
        k: v for k, v in packet.items() if k != "offer"
    }:
        raise ValueError("near wrong offer changed evidence beyond tile location")
    paths = next(p for q, p in jobs if q["id"] == stock["id"])
    return dict(query, cohort="omitted"), paths, phase.digest(parent / "requests.json")


def prepare(bundle, *, full=False):
    plan, jobs = _PLAN(bundle)
    phase = base.phase
    old_marginal = REFINEMENT / "marginal-offset" / "plan.json"
    old_anchor = REFINEMENT / "anchor-clock" / "plan.json"
    excluded = {q["recording"] for q in phase._read(old_marginal)["cases"]}
    excluded.update(phase._read(old_anchor)["prospective"])
    excluded.update(phase.corpus._selection("roof16")[0])
    roofs = [
        q["id"] for q in plan["cases"] if q["cohort"] == "roof"
        and q["id"].startswith("DS26-") and q["id"] not in excluded
    ]
    roofs = sorted(roofs, key=rank)[:10]
    omitted = sorted((q["id"] for q in plan["cases"] if q["cohort"] == "omitted"), key=rank)[:2]
    near, paths, near_hash = _near(plan, jobs)
    chosen = roofs[:4] + omitted + [near["id"]] + roofs[4:]
    if not full:
        entries = {q["id"]: (q, files) for q, files in jobs}
        entries[near["id"]] = near, paths
        jobs = [entries[ident] for ident in chosen]
    identity = {}
    paths = (
        Path(__file__), WORKER, Path(clock_offset.__file__), Path(clock_offset.offset.__file__),
    )
    for path in paths:
        identity[str(path.relative_to(ROOT))] = phase.digest(path)
    ids = dict(first=roofs[:4], reserve=roofs[4:], omitted=omitted + [near["id"]])
    current = dict(
        plan, cases=[q for q, _ in jobs], cpus=list(CPUS), opaque_selector=SALT,
        study_stage="full" if full else "challenge", challenge=ids,
        challenge_near_request_sha256=near_hash, implementation=identity,
        formula_sha256=phase.digest(REPORT / "PROTOCOL.md"),
        models=list(clock_offset.MODES),
    )
    return current, jobs


def command(cpu, paths, bundle):
    argv = _COMMAND(cpu, paths, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    for module in (clock_offset, clock_offset.offset):
        path = Path(module.__file__)
        argv[-3:-3] = ["--ro-bind", str(path), f"/worker/tools/pipeline_eval/variants/{path.name}"]
    return argv


def bindings(query):
    return dict(_BIND(query), method=clock_offset.METHOD)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--bundle", type=Path, default=base.base.BUNDLE)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    with (
        patch.object(base, "prepare", lambda bundle: prepare(bundle, full=args.full)),
        patch.object(base, "command", command), patch.object(base, "bindings", bindings),
        patch.object(base, "CPUS", CPUS),
    ):
        base.run(args.work, args.bundle, REPORT / "full" if args.full else REPORT)
