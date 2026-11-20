"""Reuse the authenticated complete-IQ and original-v5 receivers on a second fresh pair."""

import argparse
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import fresh_replay as previous
from . import fresh_replay_reference as reference
from .full_v5_check import _sha

REPORT = previous.union.SCREEN / "latency-and-support/new-waveforms"
WORK = Path("/var/tmp/leo-new-waveforms-20261119")
REFERENCE_WORK = reference.WORK.with_name("new-waveforms-DS29-original-20261119")
MODULE = "tools.pipeline_eval.qualification.new_waveforms"
PREVIOUS = previous.REPORT
EARLIER_EXCLUSIONS = previous.excluded
METHOD = "new_waveforms_fifth"
STOCK = "new_waveforms_stock"


def excluded():
    cases, sources = EARLIER_EXCLUSIONS()
    for path in (
        PREVIOUS / "source-lock.json",
        previous.union.SCREEN / "latency-and-support" / "all-recordings" / "source-lock.json",
    ):
        if path.is_file():
            freeze = whole_iq.read(path)
            known = previous.union.exact_wide_iq.scheduled(freeze)
            sources[str(path.relative_to(previous.union.SCREEN))] = dict(
                cases=known,
                sha256=_sha(path),
            )
            cases.update(known)
    return cases, sources


@contextmanager
def context():
    with (
        patch.multiple(
            previous,
            REPORT=REPORT,
            WORK=WORK,
            MODULE=MODULE,
            METHOD=METHOD,
            CONTROL=STOCK,
            excluded=excluded,
        ),
        patch.multiple(reference, REPORT=REPORT, WORK=REFERENCE_WORK, MODULE=MODULE),
    ):
        yield


def freeze(work):
    with context():
        previous.freeze(work)
        path = REPORT / "source-lock.json"
        lock = whole_iq.read(path)
        lock["programs"][str(Path(__file__).relative_to(ROOT))] = _sha(Path(__file__))
        lock["independent_reference_launcher_sha256"] = _sha(Path(reference.__file__))
        save_json(path, lock)
        save_json(work / path.name, lock)
        print(_sha(path), flush=True)


def launch(work, ident):
    with context():
        previous.run(work, ident)


def references(work, reference_work):
    with context():
        plan = previous.source(work)
        whole_iq.checked(
            Path(reference.__file__),
            plan["independent_reference_launcher_sha256"],
        )
        reference.run(work, reference_work)


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
    elif args.action == "run" and args.case:
        launch(args.work, args.case)
    elif args.action == "references":
        references(args.work, args.reference_work)
    elif args.action == "worker" and args.attempt:
        with context():
            if args.cpu is None:
                previous.worker(args.attempt)
            else:
                raise SystemExit(reference.worker(args.attempt, args.cpu))
    else:
        parser.error("the run requires a case and the worker requires an attempt")
