"""Run the frozen AB/BA feature comparison with the existing admission watcher."""

import argparse
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from shutil import copyfile
import subprocess
from time import monotonic, time_ns
from unittest.mock import patch

from . import held_cfo_features_capsule as base


PROGRAMS = ("held_cfo_features.py", "held_cfo_features_trial.py", "held_cfo_ingress.py", "held_cfo_ingress_trial.py")
JOBS = ("DS30-0019:AB", "DS30-0274:BA", "DS30-0274:AB", "DS30-0019:BA")


def child(root, job, cpu, timeout):
    original = base.command

    def command(path, case, core, fd):
        argv = original(path, case, core, fd)
        index = argv.index("feature_trial.held_cfo_features_trial")
        argv[index] = "feature_trial.held_cfo_ingress_trial"
        return argv

    with patch.object(base, "command", command):
        return base.child(root, job, cpu, timeout)


def check_residency(root):
    nbytes = base.require_resident(root)
    files = [root/"program"/name for name in PROGRAMS[2:]]
    result = subprocess.check_output(["/usr/bin/fincore", "-bJ", "-o", "RES,SIZE,FILE", *map(str, files)], text=True)
    rows = json.loads(result)["fincore"]
    if len(rows) != len(files) or any(row["res"] < row["size"] for row in rows):
        raise ValueError("Require resident ingress implementation and trial")
    return nbytes + sum(row["size"] for row in rows)


def prepare(root):
    root.mkdir(mode=0o700)
    (root/"empty").mkdir()
    (root/"program/measurements").mkdir(parents=True)
    for source in (*[base.HERE/name for name in PROGRAMS], base.PLAN):
        dest = root/"program"/source.relative_to(base.HERE)
        copyfile(source, dest)
        dest.chmod(0o400)
    base.sock_filter(root/"sockets.bpf")
    nbytes = check_residency(root)
    check = child(root, "proof", 3, 5.)
    evidence = check["result"]
    if (evidence["network_namespace"] == os.readlink("/proc/self/ns/net")
            or evidence["mount_namespace"] == os.readlink("/proc/self/ns/mnt")):
        raise ValueError("The ingress worker shares the outer namespace")
    pins = {name: sha256((root/"program"/name).read_bytes()).hexdigest() for name in PROGRAMS}
    base.write(root/"preflight.json", dict(resident_bytes=nbytes, complete_graphs=0, sources=pins, **check))


def admit(root, pid, event):
    with base.LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        body = base.checked_bytes(base.CAMPAIGN/event["event"], event["event_sha256"][7:])
        if json.loads(body)["state"] != "deferred_storage_busy":
            raise ValueError("Require the exact official deferral event")
        base.idle(pid)
        age = time_ns()-event["unix_ns"]
        if not 0 <= age <= base.FRESH_NS:
            raise ValueError("Official deferral no longer leaves the protected sleep window")
        started = monotonic()
        results = []
        for job in JOBS:
            result = child(root, job, 2, max(0., base.LIMIT-(monotonic()-started)))
            base.write(root/f"{job.replace(':', '-')}.json", result)
            results.append(result)
        base.write(root/"timing.json", dict(deferral=event, initial_age_ns=age, driver_pid=pid,
                                           exclusive_slot_wall_s=monotonic()-started,
                                           required_stop_seconds=base.LIMIT, results=results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--watch-driver", type=int)
    args = parser.parse_args()
    root = args.root
    if root.parent != Path("/dev/shm"):
        parser.error("Use one private tmpfs proof root")
    if args.watch_driver is None:
        prepare(root)
        return
    if not (root/"preflight.json").is_file() or (root/"watch-start.json").exists():
        parser.error("Require one successful preflight before starting each watch")
    preflight = json.loads((root/"preflight.json").read_bytes())
    for name, pin in preflight["sources"].items():
        base.checked_bytes(root/"program"/name, pin)
        base.checked_bytes(base.HERE/name, pin)
    check_residency(root)
    with patch.object(base, "admit", admit):
        base.watch(root, args.watch_driver)


if __name__ == "__main__":
    main()
