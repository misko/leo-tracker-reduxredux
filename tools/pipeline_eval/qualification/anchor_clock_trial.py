"""Seal the same-anchor receiver clock comparison over all native queries."""

import argparse
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ..variants import anchor_clock
from . import native_clock_full as base

WORKER = Path(__file__).with_name("anchor_clock_worker.py")
REPORT = base.base.native.ROOT / "reports/2026_11_19_receiver_screening/refinement/anchor-clock"
WORK = base.WORK.with_name("native-anchor-clock-pair")
CPUS = (12, 13, 14, 15)
ANCHOR_SHA256 = "702517334664b9c4b097009d27932202cb1a81348ec76dd14b136f12912345ad"
_PLAN, _COMMAND, _BIND = base.prepare, base.command, base.bindings
SALT = "anchor-clock-prospective-v1:"


def prepare(bundle):
    plan, jobs = _PLAN(bundle)
    phase = base.phase
    old = REPORT.with_name("anchor-receiver") / "source-lock.json"
    historical = phase._read(old)
    anchor = Path(anchor_clock.anchor.__file__)
    scoped = historical["files"][str(anchor.relative_to(base.base.native.ROOT))]
    if phase.digest(anchor) != ANCHOR_SHA256 or scoped != ANCHOR_SHA256:
        raise ValueError("the independent anchor selection source changed")
    excluded = {case for group in historical["cohorts"].values() for case in group}
    old_roof = phase.corpus._selection("roof16")[0]
    eligible = [
        q["id"] for q in plan["cases"] if q["cohort"] == "roof"
        and q["id"].startswith("DS26-") and q["id"] not in excluded | set(old_roof)
    ]
    prospective = sorted(eligible, key=lambda case: sha256((SALT + case).encode()).digest())[:6]
    wrong = [q["id"] for q in plan["cases"] if q["cohort"] == "omitted"]
    priority = {ident: i for i, ident in enumerate([*prospective, *wrong])}
    jobs = sorted(jobs, key=lambda job: priority.get(job[0]["id"], len(priority)))
    identities = dict(
        anchor=ANCHOR_SHA256, anchor_prepared_source_lock=phase.digest(old),
        trial=phase.digest(Path(__file__)), worker=phase.digest(WORKER),
        implementation=phase.digest(Path(anchor_clock.__file__)),
        protocol=phase.digest(REPORT / "PROTOCOL.md"),
    )
    return dict(
        plan, cpus=list(CPUS), anchor_clock_source=identities, prospective=prospective,
        selector=SALT, execution_order=[q["id"] for q, _ in jobs],
    ), jobs


def command(cpu, paths, bundle):
    argv = _COMMAND(cpu, paths, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    for module in (anchor_clock, anchor_clock.anchor):
        path = Path(module.__file__)
        argv[-3:-3] = ["--ro-bind", str(path), f"/worker/tools/pipeline_eval/variants/{path.name}"]
    return argv


def bindings(query):
    return dict(_BIND(query), method=anchor_clock.METHOD, variant=anchor_clock.METHOD)


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
