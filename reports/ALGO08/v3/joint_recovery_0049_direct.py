"""Attempt the sealed, unused joint saved worker with direct idle checks."""

import argparse
import runpy
import sys
from dataclasses import asdict
from pathlib import Path
from time import monotonic, sleep, time_ns

sys.path.insert(0, str(Path(__file__).resolve().parent))

from joint_recovery_0049_admission import QUIET, QUIET_PIN, device_stats
from matched_donor_0049_trial import (
    BUILD,
    BUILD_PIN,
    JOINT,
    STAGE,
    document,
    identifier,
    launch,
    require_resident,
    write,
)

DRIVER = QUIET.with_name("ds30_paired_evaluation.py")
PLAN_PIN = "cd8ec992ec3706e580d92607ab6c506e599d184265ea35c37ed2a9cb12bef84e"
WATCH_PIN = "2d231d7f01c2f654f10b5aca7021c64f21209be416268bfbdc5e45a384b7325a"


def require_driver_idle(pid):
    proc = Path("/proc")/str(pid)
    argv = (proc/"cmdline").read_bytes().split(b"\0")
    if not any(arg.decode() == str(DRIVER) and argv[i+1] == b"run"
               for i,arg in enumerate(argv[:-1])):
        raise ValueError("The enrolled driver is not running the original paired entry")
    children = (proc/"task"/str(pid)/"children").read_text().split()
    if children:
        raise ValueError(f"The enrolled driver has active children {children}")


def check_quiet():
    if identifier(QUIET) != QUIET_PIN:
        raise ValueError("Official quiet guard identity changed")
    scope = runpy.run_path(str(QUIET))
    devices = device_stats(Path("/proc/self/mountinfo").read_text().splitlines())
    guards = {name: scope["QuietInterval"]() for name in devices}
    deadline = monotonic()+1.75
    while monotonic() < deadline:
        states = {name: scope["sample"](path, monotonic) for name,path in devices.items()}
        ready = []
        for name, state in states.items():
            guard = guards[name]
            ready.append(guard.observe(state))
            queue, pressure = guard.queue_mean, guard.current_full
            if (guard.since is None or queue is not None and (
                not 0 <= queue <= scope["QUEUE_LIMIT"]
                or not 0 <= pressure < scope["FULL_LIMIT"]
            )):
                raise ValueError(f"Nonquiet {name}: {asdict(state)}, queue={queue}, psi={pressure}")
        if all(ready):
            return {name: dict(asdict(state), queue_mean=guards[name].queue_mean,
                               interval_full_pct=guards[name].current_full)
                    for name,state in states.items()}
        sleep(scope["POLL_S"])
    raise ValueError("No one-second continuously quiet interval in the direct check")


def require_cached():
    staged = STAGE/"tle"
    build = document(BUILD, BUILD_PIN)
    portable = Path(build["native"]["--portable-orbit-index"]["path"]).resolve(strict=True)
    files = [path.resolve(strict=True) for path in staged.glob("archive/space-track/*.tle")]
    if len(files) != 48 or any(not path.is_relative_to(staged) for path in files):
        raise ValueError("The previously verified resident catalogue is incomplete")
    if not portable.is_relative_to("/dev/shm"):
        raise ValueError("Require the already verified local portable operand")
    require_resident([portable, *files])
    return dict(tle_files=len(files),
                portable_sha256=build["native"]["--portable-orbit-index"]["sha256"])


def attempt(root, pid):
    if any((root/name).exists() for name in (
        "prediction-seal.json", "worker.stdout", "direct-admission.json",
    )):
        raise ValueError("The joint job or direct attempt has already been used")
    old = document(root/"watch.json", WATCH_PIN)
    if old["status"] != "no_fresh_official_storage_deferral" or old["plan_sha256"] != PLAN_PIN:
        raise ValueError("Require the preserved first watch receipt and untouched science plan")
    begin, evidence = time_ns(), {}

    def admit():
        require_driver_idle(pid)
        evidence["quiet"] = check_quiet()
        evidence["cache"] = require_cached()
        require_driver_idle(pid)
        return dict(evidence, driver_pid=pid, verified_no_active_children=True)

    try:
        launch(root, PLAN_PIN, JOINT, admission=admit)
    except (OSError, ValueError) as error:
        status = dict(disposition="blocked_or_failed", reason=str(error))
    else:
        status = dict(disposition="prediction_sealed")
    print(write(root/"direct-admission.json", dict(
        status, evidence=evidence, plan_sha256=PLAN_PIN, first_watch_sha256=WATCH_PIN,
        began_ns=begin, ended_ns=time_ns(), driver_pid=pid, attempts=1,
        worker_started=(root/"clock.json").exists(),
    )))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("driver_pid", type=int)
    args = parser.parse_args()
    attempt(args.root, args.driver_pid)
