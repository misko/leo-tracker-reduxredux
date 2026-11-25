"""One bounded live deferral window for the saved-factor timing only."""

import argparse
import ctypes
import fcntl
import json
import os
from pathlib import Path
import resource
import select
import subprocess
import sys
from time import monotonic, time_ns

from .field_crossover_admission_watch import CAMPAIGN, MOVED_TO, recent_deferral, replaced_export


LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
WATCH_SECONDS = 55
FRESH_NS = 2_000_000_000
CAP_SECONDS = 15


def launch(event, binary, pin, *, proof, physical):
    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if time_ns()-event["unix_ns"] > FRESH_NS:
            raise ValueError("The official deferral expired")
        command = ["taskset", "-c", "2", "nice", "-n", "15", "ionice", "-c", "3",
                   sys.executable, "-B", "-m", "reports.ALGO08.v3.profiled_grid_export_check",
                   "--timing-library", str(binary), "--sha256", pin, "--lease-fd", str(lease.fileno()),
                   "--admission-ns", str(event["unix_ns"])]
        if proof:
            command.append("--proof-prefix")
        if physical:
            command.extend(("--physical-0008", *physical))
        started = monotonic()
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        try:
            child = subprocess.run(command, pass_fds=(lease.fileno(),), capture_output=True, text=True,
                                   timeout=CAP_SECONDS, check=False)
            result = dict(returncode=child.returncode, stdout=child.stdout, stderr=child.stderr)
        except subprocess.TimeoutExpired as failure:
            result = dict(returncode=124, stdout=(failure.stdout or b"").decode(),
                          stderr=(failure.stderr or b"").decode())
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        return dict(result, elapsed_s=monotonic()-started,
                    cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                    input_blocks=after.ru_inblock-before.ru_inblock,
                    major_faults=after.ru_majflt-before.ru_majflt, admitted=event)


def watch(binary, pin, *, proof, physical, official_case=None):
    if not binary.is_file():
        raise ValueError("Prebuild the audited native binary before the watch")
    return observe(lambda event: launch(event, binary, pin, proof=proof, physical=physical), official_case)


def observe(admit, official_case, *, seconds=WATCH_SECONDS):
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "inotify_init1")
    try:
        if libc.inotify_add_watch(fd, os.fsencode(CAMPAIGN), MOVED_TO) < 0:
            raise OSError(ctypes.get_errno(), "inotify_add_watch")
        started, deadline = time_ns(), monotonic()+seconds
        exports = 0
        while (remaining := deadline-monotonic()) > 0:
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable or not replaced_export(os.read(fd, 65536)):
                continue
            exports += 1
            event = recent_deferral(CAMPAIGN, started, time_ns())
            if (event is not None and (official_case is None or event["case"] == official_case)
                    and time_ns()-event["unix_ns"] <= FRESH_NS):
                try:
                    return dict(admit(event), attempts=1, exports=exports, watching_from=started)
                except (OSError, ValueError) as failure:
                    return dict(status="single_attempt_declined", reason=str(failure), candidate=event,
                                attempts=1, exports=exports, watching_from=started)
        return dict(status="no_fresh_official_storage_deferral", attempts=0, exports=exports, watching_from=started)
    finally:
        os.close(fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("--proof-prefix", action="store_true")
    parser.add_argument("--physical-0008", nargs=2, metavar=("CORRECTNESS_JSON", "SHA256"))
    parser.add_argument("--official-case", help="Limit admission to a deferral of this original case")
    args = parser.parse_args()
    print(json.dumps(watch(args.binary, args.sha256, proof=args.proof_prefix, physical=args.physical_0008,
                           official_case=args.official_case), sort_keys=True))
