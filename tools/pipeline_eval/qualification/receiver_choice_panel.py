"""Freeze two new lower-edge recordings for direct receiver policy replays."""

import argparse
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ROLES
from . import fresh_replay as whole
from . import fresh_replay_reference as reference
from . import new_waveforms as previous
from .full_v5_check import _sha

REPORT = whole.union.SCREEN / "receiver-choice/fresh-panel"
WORK = Path("/var/tmp/leo-receiver-choice-fresh-20261119")
REFERENCE_WORK = reference.WORK.with_name("receiver-choice-DS29-original-20261119")
MODULE = "tools.pipeline_eval.qualification.receiver_choice_panel"
METHOD = "receiver_choice_five"
STOCK = "receiver_choice_four"
CPUS = {"DS26": [12, 13], "DS29": [14, 15]}
LANES = {16: (ROLES[0], ROLES[3]), 17: (ROLES[1], ROLES[2])}
DS26_ROSTER, DS29_ROSTER = whole.ds26_roster, whole.ds29_roster
ARCHIVE = whole.archive_ok


def exclusions():
    cases, sources = previous.excluded()
    for name, field in (
        ("latency-and-support/new-waveforms/source-lock.json", "cases"),
        ("latency-and-support/fifth-completion/source-lock.json", "cases"),
        ("latency-and-support/complete-roster/roster.json", "all"),
        ("latency-and-support/complete-timing/prediction-lock.json", "cases"),
        ("acquisition-support/fresh-waveform/source-lock.json", "cases"),
    ):
        path = whole.union.SCREEN / name
        ledger = whole_iq.read(path)
        known = (
            sorted(ledger[field]) if field == "all" else whole.union.exact_wide_iq.scheduled(ledger)
        )
        sources[name] = dict(cases=known, sha256=_sha(path))
        cases.update(known)
    return cases, sources


def lower_edge(provider, excluded):
    ranked, ledger = provider(excluded)
    eligible = []
    for digest, ident, case in ranked:
        segment = Path(case["recording"]["segments"][0]["path"]).parent.parent.name
        edge = segment.rsplit("-", 1)[-1]
        ledger[ident]["archive_edge_name"] = edge
        if edge == "lower":
            eligible.append((digest, ident, case))
        else:
            ledger[ident]["state"] = "different or undocumented archive edge"
    return eligible, ledger


def requires_lower(case):
    capture, files = ARCHIVE(case)
    if capture["edge"] != "lower":
        raise ValueError("signed pilot edge differs from lower-edge acquisition stratum")
    return capture, files


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
            excluded=exclusions,
            ds26_roster=lambda excluded: lower_edge(DS26_ROSTER, excluded),
            ds29_roster=lambda excluded: lower_edge(DS29_ROSTER, excluded),
            archive_ok=requires_lower,
        ),
        patch.multiple(reference, REPORT=REPORT, WORK=REFERENCE_WORK, MODULE=MODULE, LANES=LANES),
    ):
        yield


def freeze(work):
    # Collect history before rebinding the legacy source path used by previous.excluded.
    history = exclusions()
    with context(), patch.object(whole, "excluded", lambda: history):
        whole.freeze(work)
        path = REPORT / "source-lock.json"
        lock = whole_iq.read(path)
        for file in (Path(__file__), Path(reference.__file__)):
            lock["programs"][str(file.relative_to(ROOT))] = _sha(file)
        save_json(work / path.name, lock)
        save_json(path, lock)
        print(_sha(path), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "references", "worker"))
    parser.add_argument("attempt", type=local_output, nargs="?")
    parser.add_argument("cpu", type=int, nargs="?")
    parser.add_argument("--work", type=local_output, default=WORK)
    parser.add_argument("--reference-work", type=local_output, default=REFERENCE_WORK)
    parser.add_argument("--case")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        with context():
            if args.action == "run" and args.case:
                whole.run(args.work, args.case)
            elif args.action == "references":
                reference.run(args.work, args.reference_work)
            elif args.action == "worker" and args.attempt:
                if args.cpu is None:
                    whole.worker(args.attempt)
                else:
                    raise SystemExit(reference.worker(args.attempt, args.cpu))
            else:
                parser.error("a replay requires a case and a worker requires an attempt")
