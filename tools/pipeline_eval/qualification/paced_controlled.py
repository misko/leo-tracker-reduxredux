"""Run four counterbalanced live receiver clocks against the verified local IQ spool."""

import argparse
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from . import arrival_queue as pace
from . import equal_pace as detector
from . import paced_controlled_source as external
from .full_v5_check import _sha

REPORT = external.REPORT
WORK = Path("/var/tmp/leo-paced-controlled-20261119")
MODULE = "tools.pipeline_eval.qualification.paced_controlled"
CASE = external.CASE
ORDER = (
    ("BA", detector.MIXED),
    ("BA", detector.FOUR),
    ("AB", detector.FOUR),
    ("AB", detector.MIXED),
)


def freeze(work, source):
    if work.exists() or (REPORT / "source-lock.json").exists():
        raise FileExistsError("the controlled pacing study already has a launch lock")
    old = whole_iq.read(whole_iq.checked(detector.REPORT / "source-lock.json", external.OLD_SHA))
    ready = whole_iq.read(source / "ready.json")
    prior = old["cases"][CASE]
    group = ready["end"]["cgroup"]
    stage = whole_iq.read(REPORT / "source-stage-lock.json")
    if (
        old["case"] != CASE
        or ready["case"] != CASE
        or old["order"] != [detector.MIXED, detector.FOUR]
        or ready["raw_recording_sha256"] != prior["raw_recording_sha256"]
        or ready["bytes"] != stage["iq_bytes"]
        or stage["input"]["capture"] != prior["capture"]
        or external.charge(group)["memory.stat.shmem"] < ready["bytes"]
    ):
        raise ValueError("the ready source does not authenticate against the sealed former replay")
    names = ("members.json.gz", "ready.json")
    for n in names:
        write(REPORT / n, (source / n).read_bytes())
    for row in prior["modes"].values():
        name = row["events"]
        write(REPORT / name, whole_iq.checked(detector.REPORT / name, row["sha256"]).read_bytes())
    spec = dict(prior, staged_source=str(source), staged_ready_sha256=_sha(source / "ready.json"))
    paths = (
        Path(__file__),
        Path(external.__file__),
        Path(detector.__file__),
        Path(pace.__file__),
        REPORT / "PROTOCOL.md",
        REPORT / "source-stage-lock.json",
        *[REPORT / n for n in names],
    )
    doc = dict(
        old,
        cases={CASE: spec},
        order=[dict(pair=pair, role=role) for pair, role in ORDER],
        programs=old["programs"] | {str(n.relative_to(ROOT)): _sha(n) for n in paths},
        source_cgroup=group,
        source_cap_bytes=external.CAP,
        former_source_sha256=external.OLD_SHA,
        source_ready_sha256=_sha(REPORT / "ready.json"),
    )
    work.mkdir(parents=True, exist_ok=False)
    save_json(REPORT / "source-lock.json", doc)
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(REPORT / "source-lock.json")))


def plan(work):
    # Earlier publications use absolute program names. New entries stay workspace-relative.
    return pace.plan(work, REPORT)


def work_paths(work):
    return [(pair, role, work / pair / CASE / role) for pair, role in ORDER]


def run(work):
    locked = plan(work)
    if locked["order"] != [dict(pair=pair, role=role) for pair, role in ORDER]:
        raise ValueError("counterbalanced measurement order changed after locking")
    src = locked["source_cgroup"]
    with patch.object(pace, "MODULE", MODULE), patch.object(pace.iq_service, "MODULE", MODULE):
        for pair, role, out in work_paths(work):
            stats = dict(start=external.charge(src))
            pace.launch(out, locked["cases"][CASE], role, locked["assets"], REPORT)
            stats["end"] = external.charge(src)
            save_json(REPORT / f"raw/{pair}/{role}/source-charge.json", stats)


def worker(attempt):
    spec = whole_iq.read(attempt / "plan.json")["case"]
    folder = Path(spec["staged_source"])
    ready = whole_iq.read(whole_iq.checked(folder / "ready.json", spec["staged_ready_sha256"]))
    if ready["raw_recording_sha256"] != spec["raw_recording_sha256"]:
        raise ValueError("receiver did not receive the declared staged original IQ")

    def packets(capture, verified):
        if capture != spec["capture"] or verified:
            raise ValueError("the staged source may serve only its exact original recording")
        yield from external.packets(folder)

    with (
        detector.configure(attempt),
        patch.multiple(pace, MODULE=MODULE, packets=packets),
        patch.object(pace.iq_service, "MODULE", MODULE),
    ):
        pace.execute(attempt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("--source", type=local_output, default=external.SOURCE)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work, args.source)
    else:
        {"run": run, "worker": worker}[args.action](args.work)
