"""Replay the sealed one-slot waveform cohort with four waiting slots."""

import argparse
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import arrival_queue as paced
from .full_v5_check import _sha

REPORT = paced.PARENT.parent.parent / "arrival-and-timing/buffered-replay"
BASE = paced.REPORT
BASE_STAGE = "97d798202a4dc7096043c9d3210402ee7e0449a37b0ce388589d5a206d543164"
BASE_POSITIONS = "fcbad099e1fa8576446c8663eff70cb63ddf3c6c551b57aae35ab8c981943515"
WAITING = 4
MODULE = "tools.pipeline_eval.qualification.buffered_arrival_replay"


def config():
    return patch.multiple(paced, WAITING=WAITING, MODULE=MODULE)


def freeze(work, report):
    source = report / "source-lock.json"
    if work.exists() or source.exists():
        raise FileExistsError("four-slot retry needs a new immutable study directory")
    previous = whole_iq.read(whole_iq.checked(BASE / "stage-lock.json", BASE_STAGE))
    positions = whole_iq.read(whole_iq.checked(BASE / "position-score-lock.json", BASE_POSITIONS))
    if positions["files"]["stage-lock.json"] != BASE_STAGE:
        raise ValueError("the one-slot position study did not use the bound paced inputs")
    previous_source = whole_iq.checked(BASE / source.name, previous["files"][source.name])
    lock = whole_iq.read(previous_source)
    if lock["waiting_slots"] != 1 or set(lock["cases"]) != set(paced.CPUS):
        raise ValueError("expected both recordings with the previously measured one-slot policy")
    for spec in lock["cases"].values():
        for mode in spec["modes"].values():
            name = mode["events"]
            if previous["files"][name] != mode["sha256"]:
                raise ValueError("one-slot and four-slot delivery data differ")
            write(report / name, whole_iq.checked(BASE / name, mode["sha256"]).read_bytes())
    programmes = {str(p): _sha(p) for p in (Path(__file__), report / "PROTOCOL.md")}
    save_json(
        source,
        dict(
            lock,
            waiting_slots=WAITING,
            programs=lock["programs"] | programmes,
            one_slot_stage_sha256=BASE_STAGE,
            one_slot_position_sha256=BASE_POSITIONS,
        ),
    )
    work.mkdir(parents=True)
    save_json(work / "launch-lock.json", {"source_lock_sha256": _sha(source)})


def run(work, report):
    with config():
        if paced.plan(work, report)["waiting_slots"] != paced.WAITING:
            raise ValueError("runtime queue capacity differs from the prospective lock")
        paced.replay(work, report)


def worker(attempt):
    with config():
        paced.execute(attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("freeze", "replay"):
        entry = commands.add_parser(action)
        entry.add_argument("work", type=local_output)
        entry.add_argument("--out", type=local_output, default=REPORT)
    commands.add_parser("worker").add_argument("attempt", type=local_output)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.attempt)
    else:
        {"freeze": freeze, "replay": run}[args.action](args.work, args.out)


if __name__ == "__main__":
    main()
