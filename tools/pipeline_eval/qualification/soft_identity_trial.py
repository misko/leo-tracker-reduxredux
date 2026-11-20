"""Freeze an anonymous soft-mixture receiver on stored native-factor requests."""

import argparse
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ..variants import soft_identity
from . import clock_offset_trial
from . import native_clock_full as base

ROOT = base.base.native.ROOT
SCREENING = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREENING / "redesign/soft-identity"
WORK = base.WORK.with_name("native-soft-identity-challenge")
WORKER = Path(__file__).with_name("soft_identity_worker.py")
CPUS = (0, 2, 3, 6)
SALT = "soft-identity-reserve-v1:"
DIAGNOSTIC = ("DS26-0036", "DS29-0082")
CONTROL = "native_soft_identity_exact_control"
_PLAN, _COMMAND, _BIND = base.prepare, base.command, base.bindings


def rank(ident):
    return sha256((SALT + ident).encode()).digest()


def prepare(bundle, *, full=False):
    plan, jobs = _PLAN(bundle)
    phase = base.phase
    historical_paths = (
        SCREENING / "recovery/clock-offset/plan.json",
        SCREENING / "refinement/anchor-clock/plan.json",
        SCREENING / "refinement/anchor-receiver/source-lock.json",
        SCREENING / "refinement/marginal-offset/plan.json",
    )
    clock, anchor, prepared, offset = [phase._read(path) for path in historical_paths]
    excluded = set(phase.corpus._selection("roof16")[0]) | set(anchor["prospective"])
    excluded.update(i for cases in clock["challenge"].values() for i in cases)
    excluded.update(i for cases in prepared["cohorts"].values() for i in cases)
    excluded.update(q["recording"] for q in offset["cases"])
    pairs = {q["id"]: (q, paths) for q, paths in jobs}
    eligible = [
        q["id"] for q in plan["cases"]
        if q["cohort"] == "roof" and q["id"].startswith("DS26-") and q["id"] not in excluded
    ]
    reserve = sorted(eligible, key=rank)[:8]
    omitted = sorted((q["id"] for q in plan["cases"] if q["cohort"] == "omitted"), key=rank)[:2]
    if len(reserve) != 8 or len(omitted) != 2:
        raise ValueError("incomplete independent reserve or distant omitted roster")
    close, paths, near_receipt = clock_offset_trial._near(plan, jobs)
    if not full:
        pairs[close["id"]] = close, paths
        priority = [*DIAGNOSTIC, *omitted, close["id"], *reserve]
        jobs = [pairs[ident] for ident in priority]
    files = [Path(__file__), WORKER, Path(soft_identity.__file__), REPORT / "PROTOCOL.md"]
    return dict(
        plan, cases=[q for q, _ in jobs], cpus=list(CPUS), method=soft_identity.METHOD,
        study_stage="full" if full else "challenge",
        challenge=dict(
            diagnostic=list(DIAGNOSTIC), reserve=reserve, omitted=omitted + [close["id"]],
        ),
        source_files={str(path.relative_to(ROOT)): phase.digest(path) for path in files},
        previous_rosters={str(p.relative_to(ROOT)): phase.digest(p) for p in historical_paths},
        close_binding_sha256=near_receipt, selector=SALT,
    ), jobs


def command(cpu, paths, bundle):
    argv = _COMMAND(cpu, paths, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    source = Path(soft_identity.__file__)
    argv[-3:-3] = ["--ro-bind", str(source), f"/worker/tools/pipeline_eval/variants/{source.name}"]
    return argv


def bindings(query):
    return dict(_BIND(query), method=soft_identity.METHOD)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--bundle", type=Path, default=base.base.BUNDLE)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    with (
        patch.object(base, "prepare", lambda path: prepare(path, full=args.full)),
        patch.object(base, "command", command), patch.object(base, "bindings", bindings),
        patch.object(base, "CPUS", CPUS),
    ):
        base.run(args.work, args.bundle, REPORT / "full" if args.full else REPORT)
