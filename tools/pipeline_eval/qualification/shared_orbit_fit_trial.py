"""Seal the paired shared-satellite timing study before observing scores."""

import argparse
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ..variants import shared_orbit_fit
from . import native_clock_full as base
from . import soft_identity_trial as prior

ROOT = base.base.native.ROOT
REPORT = ROOT / "reports/2026_11_19_receiver_screening/deployment/shared-orbit-fit"
WORK = base.WORK.with_name("native-shared-orbit-fit")
WORKER = Path(__file__).with_name("shared_orbit_fit_worker.py")
CPUS = (4, 5, 6, 7)
SALT = "shared-orbit-fit-reserve-v1:"
EXACT = "joint_orbits"
METHODS = shared_orbit_fit.METHOD, shared_orbit_fit.soft.METHOD, EXACT
_PLAN, _COMMAND, _BIND = base.prepare, base.command, base.bindings


def rank(ident):
    return sha256((SALT + ident).encode()).digest()


def close(phase, stock, old):
    root = prior.SCREENING / "refinement/boundary-roof/reserve"
    path = root / "requests.json"
    requests = phase._read(path)
    evaluator = root / "evaluator.json"
    if (
        phase.digest(evaluator) != requests["evaluator_sha256"]
        or requests["clock_plan_sha256"] != phase.digest(base.REPORT / "plan.json")
    ):
        raise ValueError("unbound historical near-outside offer")
    valid = {r["id"] for r in phase._read(evaluator)["labels"]
             if r["condition"] == "near-outside" and r["id"] not in old}
    ident = min(valid, key=rank)
    query = next(x for x in requests["cases"] if x["id"] == ident)
    original, paths = stock[query["recording"]]
    if dict(query["packet"], offer=original["packet"]["offer"]) != original["packet"]:
        raise ValueError("close offer changed evidence beyond the tile")
    return dict(query, cohort="omitted"), paths, phase.digest(path)


def prepare(bundle):
    original, original_jobs = _PLAN(bundle)
    phase = base.phase
    prior_lock = prior.REPORT / "prediction-lock.json"
    receipt = phase._read(prior_lock)
    base.base.secant_full._verify_files(prior.REPORT, receipt["files"])
    old = phase._read(prior.REPORT / "plan.json")
    if (
        set(receipt["cases"]) != {q["id"] for q in old["cases"]}
        or phase.digest(Path(shared_orbit_fit.soft.__file__))
        != old["source_files"][str(Path(shared_orbit_fit.soft.__file__).relative_to(ROOT))]
    ):
        raise ValueError("the old soft study or implementation differs from its sealed release")
    stock = {q["id"]: (q, p) for q, p in original_jobs}
    prior_jobs = []
    for query in old["cases"]:
        raw, paths = stock[query["id"]] if query["id"] in stock else stock[query["recording"]]
        if dict(query["packet"], offer=raw["packet"]["offer"]) != raw["packet"]:
            raise ValueError("old diagnosed query changed reference evidence")
        prior_jobs.append((query, paths))
    excluded = {q["recording"] for q in old["cases"]}
    excluded.update(phase.corpus._selection("roof16")[0])
    clock = phase._read(prior.SCREENING / "recovery/clock-offset/plan.json")
    excluded.update(i for cohort in ("first", "reserve") for i in clock["challenge"][cohort])
    anchor = phase._read(prior.SCREENING / "refinement/anchor-clock/plan.json")
    excluded.update(anchor["prospective"])
    new = sorted(
        (q["id"] for q, _ in original_jobs if q["cohort"] == "roof"
         and q["id"].startswith("DS26-") and q["id"] not in excluded),
        key=rank,
    )[:8]
    far = sorted(
        (q["id"] for q, _ in original_jobs if q["cohort"] == "omitted"
         and q["id"] not in receipt["cases"]), key=rank,
    )[:2]
    near, paths, near_digest = close(phase, stock, set(receipt["cases"]))
    jobs = [*(stock[i] for i in new + far), (near, paths), *prior_jobs]
    if len(new) != 8 or len(far) != 2 or len({q["id"] for q, _ in jobs}) != 24:
        raise ValueError("the locked new and diagnosed challenge rosters must be disjoint")
    files = (
        Path(__file__), WORKER, Path(shared_orbit_fit.__file__),
        Path(shared_orbit_fit.soft.__file__), REPORT / "PROTOCOL.md",
    )
    cohorts = dict(
        new_roof=new, new_wrong=far + [near["id"]],
        diagnosed_roof=[q["id"] for q, _ in prior_jobs if q["cohort"] == "roof"],
        diagnosed_wrong=[q["id"] for q, _ in prior_jobs if q["cohort"] == "omitted"],
    )
    return dict(
        original, cases=[q for q, _ in jobs], cohorts=cohorts, cpus=list(CPUS),
        source_files={str(p.relative_to(ROOT)): phase.digest(p) for p in files},
        prior_soft_sha256=phase.digest(prior_lock), reserve_selector=SALT,
        close_binding_sha256=near_digest, methods=list(METHODS),
    ), jobs


def command(cpu, paths, bundle):
    argv = _COMMAND(cpu, paths, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    for module in (shared_orbit_fit, shared_orbit_fit.soft):
        source = Path(module.__file__)
        target = f"/worker/tools/pipeline_eval/variants/{source.name}"
        argv[-3:-3] = ["--ro-bind", str(source), target]
    return argv


def bindings(query):
    return dict(_BIND(query), method=shared_orbit_fit.METHOD)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--bundle", type=Path, default=base.base.BUNDLE)
    args = parser.parse_args()
    with (
        patch.object(base, "prepare", prepare), patch.object(base, "command", command),
        patch.object(base, "bindings", bindings), patch.object(base, "CPUS", CPUS),
    ):
        base.run(args.work, args.bundle, REPORT)
