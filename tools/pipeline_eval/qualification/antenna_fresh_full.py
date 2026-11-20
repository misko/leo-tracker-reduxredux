"""Freeze new complete saved waveforms for dual four-center and partner-on-hit."""

import argparse
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ROLES
from ..variants import one_lane_schedule, partner_on_hit, second_on_miss
from . import fresh_replay as whole
from . import fresh_replay_reference as reference
from . import receiver_choice_panel as previous
from .full_v5_check import _sha

REPORT = whole.union.SCREEN / "antenna-confirmation/fresh-full"
WORK = Path("/var/tmp/leo-antenna-confirmation-fresh-20261119")
REFERENCE_WORK = reference.WORK.with_name("antenna-confirmation-DS29-original-20261119")
MODULE = "tools.pipeline_eval.qualification.antenna_fresh_full"
METHOD = "fresh_full_partner_on_hit"
STOCK = "fresh_full_dual_four"
CPUS = {"DS26": [2, 3], "DS29": [4, 5]}
LANES = {22: (ROLES[0], ROLES[3]), 23: (ROLES[1], ROLES[2])}
LIMIT_S = 300


def excluded():
    cases, sources = previous.exclusions()
    for name in (
        "receiver-choice/fresh-panel/source-lock.json",
        "receiver-choice/staggered-benchmark/all-figure-lock.json",
        "pilot-influence/partner-on-hit/plan.json",
    ):
        path = whole.union.SCREEN / name
        doc = whole_iq.read(path)
        known = whole.union.exact_wide_iq.scheduled(doc)
        sources[name] = dict(cases=known, sha256=_sha(path))
        cases.update(known)
    return cases, sources


@contextmanager
def context():
    with (
        patch.multiple(
            whole,
            REPORT=REPORT,
            WORK=WORK,
            MODULE=MODULE,
            METHOD=METHOD,
            CONTROL=STOCK,
            CPUS=CPUS,
            excluded=excluded,
        ),
        patch.multiple(reference, REPORT=REPORT, WORK=REFERENCE_WORK, MODULE=MODULE, LANES=LANES),
    ):
        yield


def freeze(work):
    with context():
        whole.freeze(work)
        path = REPORT / "source-lock.json"
        lock = whole_iq.read(path)
        for file in (
            Path(__file__),
            Path(reference.__file__),
            Path(partner_on_hit.__file__),
            Path(second_on_miss.__file__),
            Path(one_lane_schedule.__file__),
        ):
            lock["programs"][str(file.relative_to(ROOT))] = _sha(file)
        lock["limit_s"] = LIMIT_S
        lock["detectors"] = {"control": lock["detectors"]["control"]}
        lock["candidate_policy"] = partner_on_hit.POLICY
        lock["original_reference_cpus"] = LANES
        for entry in lock["cases"].values():
            entry["first"] = "control"
        save_json(work / path.name, lock)
        save_json(path, lock)
        print(_sha(path), flush=True)


def stock(work, ident):
    plan = whole.source(work)
    with (
        whole.patched_case(plan),
        patch.object(whole_iq, "MODULE", MODULE),
        patch.object(iq_service, "MODULE", MODULE),
    ):
        whole.union.service(work, ident, "control", plan)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "stock", "references", "worker"))
    parser.add_argument("attempt", type=local_output, nargs="?")
    parser.add_argument("cpu", type=int, nargs="?")
    parser.add_argument("--case")
    parser.add_argument("--work", type=local_output, default=WORK)
    parser.add_argument("--reference-work", type=local_output, default=REFERENCE_WORK)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        with context():
            if args.action == "stock" and args.case:
                stock(args.work, args.case)
            elif args.action == "references":
                reference.run(args.work, args.reference_work)
            elif args.action == "worker" and args.attempt:
                if args.cpu is None:
                    whole.worker(args.attempt)
                else:
                    raise SystemExit(reference.worker(args.attempt, args.cpu))
            else:
                parser.error("a service requires an attempt or recording identifier")
