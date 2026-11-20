"""Corroborate per-process RSS beside the kernel-cgroup pairs."""

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from time import monotonic
from types import FunctionType

from ..__main__ import local_output, save_json
from . import cavity_lifetime_trial as parent
from . import phase_cache_confirmation as study
from .full_receiver_comparison import read, sha


def poll_processes(roots, maxima):
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            argv = process.joinpath("cmdline").read_bytes().split(b"\0")
            if len(argv) != 10 or argv[2] != os.fsencode(study.WORKER):
                continue
            destination = Path(os.fsdecode(argv[6]))
            root = next((path for path in roots if destination.is_relative_to(path)), None)
            if root is None:
                continue
            rss = {
                k: int(v.split()[0])
                for k, _, v in (
                    line.partition(":")
                    for line in process.joinpath("status").read_text().splitlines()
                )
                if k in ("VmHWM", "VmRSS", "RssAnon")
            }
        except (OSError, ValueError):
            continue
        key = (roots[root], destination.parent.parent.name, destination.parent.name)
        measure = maxima.setdefault(key, dict(samples=0, VmHWM=0, VmRSS=0, RssAnon=0))
        measure["samples"] += 1
        for label, value in rss.items():
            measure[label] = max(measure[label], value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--paired-work", type=Path, required=True)
    args = parser.parse_args()
    work, paired = local_output(args.work), local_output(args.paired_work)
    plan_path = study.OUT / "plan.json"
    plan = read(plan_path)
    assert plan == study.lock()
    frozen = dict(plan_sha256=sha(plan_path), source_sha256=sha(Path(__file__)))
    execute = FunctionType(
        parent.execute.__code__,
        dict(
            parent.execute.__globals__,
            WORKER=study.WORKER,
            OUT=study.OUT,
            MODES=study.METHODS,
        ),
    )
    stopped = Event()
    seen = {}
    roots = {paired: "actual_second_leg", work: "repeat_first_leg"}
    begin = monotonic()

    def lane(index, ident):
        first, second = ("memo", "ordinary") if index % 2 else ("ordinary", "memo")
        while not (paired / second / ident / "attempt.json").is_file():
            if stopped.wait(0.15) or monotonic() - begin > 80:
                return None
        return execute(plan, work / first, ident, first)

    jobs = list(enumerate(plan["source"]["cases"]))
    save_json(
        study.OUT / "rss-plan.json",
        dict(
            **frozen,
            repetitions=[dict(id=ident, mode="memo" if i % 2 else "ordinary") for i, ident in jobs],
        ),
    )
    with ThreadPoolExecutor(3) as pool:
        tasks = [pool.submit(lane, index, ident) for index, ident in jobs]
        while not all(task.done() for task in tasks):
            poll_processes(roots, seen)
            stopped.wait(0.15)
    assert plan == study.lock()
    repeats = [task.result() for task in tasks]
    save_json(
        study.OUT / "rss-diagnostic.json",
        dict(
            sampled_kib=[
                dict(source=s, mode=m, id=i, **r) for (s, m, i), r in sorted(seen.items())
            ],
            repetitions=[
                None
                if r is None
                else {k: r[k] for k in ("id", "mode", "terminal", "result", "worker_wall_s")}
                for r in repeats
            ],
            wall_s=monotonic() - begin,
        ),
    )


if __name__ == "__main__":
    main()
