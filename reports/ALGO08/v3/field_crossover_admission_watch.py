"""Observe one fresh official storage deferral before one nonblocking saved launch."""

import argparse
import ctypes
from hashlib import sha256
import json
import os
from pathlib import Path
import select
from struct import Struct
import subprocess
import sys
from time import monotonic, time_ns


HERE = Path(__file__).resolve().parent
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
RUN = Path("/dev/shm/leo-v3-field-receiver-solver-cross-0220-01")
PIN = "sha256:7340a32a4722c7c03e122f2558b48fa0d98c53b36df9ff80506a136cd16980c0"
WAIT_SECONDS = 12 * 60
RECENCY_NS = 15_000_000_000
MOVED_TO = 0x80
OVERFLOW = 0x4000
RECORD = Struct("iIII")


def sha(raw):
    return "sha256:"+sha256(raw).hexdigest()


def replaced_export(raw):
    off, changed = 0, False
    while off < len(raw):
        _, mask, _, width = RECORD.unpack_from(raw, off)
        off += RECORD.size
        if mask & OVERFLOW:
            raise ValueError("Inotify notification queue overflowed")
        name = raw[off:off+width].split(b"\0", 1)[0]
        changed |= bool(mask & MOVED_TO and name == b"rows.jsonl")
        off += width
    return changed


def recent_deferral(campaign, watching_from, now):
    exported = (campaign/"rows.jsonl").read_bytes()
    rows = (json.loads(line) for line in exported.splitlines())
    cases = {row["case"] for row in rows if row["admission_state"] == "deferred_storage_busy" and not row["verified_pair"]}
    found = []
    for case in cases:
        if len(case) != 9 or not case.startswith("DS30-") or not case[5:].isdigit():
            raise ValueError("Malformed official case identifier")
        events = sorted((campaign/"cases"/case/"events").glob("*.json"))
        if not events:
            continue
        last = events[-1]
        stamp = int(last.name.split("-", 1)[0])
        if not max(watching_from, now-RECENCY_NS) < stamp <= now:
            continue
        raw = last.read_bytes()
        if json.loads(raw)["state"] == "deferred_storage_busy":
            found.append(dict(case=case, event=str(last.relative_to(campaign)), event_sha256=sha(raw),
                              unix_ns=stamp, export_sha256=sha(exported)))
    return max(found, default=None, key=lambda item: item["unix_ns"])


def write(path, row):
    with path.open("x") as out:
        json.dump(row, out, sort_keys=True, separators=(",", ":"))
        out.write("\n")


def observe():
    if sha((RUN/"admission.json").read_bytes()) != PIN or (RUN/"scratch").exists():
        raise ValueError("Require the exact prepared and unused fourth-cell admission")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_add_watch.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "inotify_init1")
    try:
        if libc.inotify_add_watch(fd, os.fsencode(CAMPAIGN), MOVED_TO) < 0:
            raise OSError(ctypes.get_errno(), "inotify_add_watch")
        watch_start, deadline = time_ns(), monotonic()+WAIT_SECONDS
        write(RUN/"watch-start.json", dict(started_unix_ns=watch_start, window_s=WAIT_SECONDS,
              method="inotify rows.jsonl renames and most recent attributable official storage event", admission=PIN,
              watcher=sha(Path(__file__).read_bytes())))
        print(f"Watching official exports for {WAIT_SECONDS} seconds", flush=True)
        replacements = 0
        while (remaining := deadline-monotonic()) > 0:
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable or not replaced_export(os.read(fd, 65536)):
                continue
            replacements += 1
            event = recent_deferral(CAMPAIGN, watch_start, time_ns())
            if event is not None:
                write(RUN/"watch-gate.json", dict(event=event, seen_unix_ns=time_ns(), exports=replacements))
                command = [sys.executable, "-IB", str(HERE/"field_receiver_solver_cross.py"), "launch", str(RUN),
                           "--case", "DS30-0220", "--pin", PIN]
                code = subprocess.run(command, check=False).returncode
                state = "saved_child_sealed" if (RUN/"prediction-seal.json").is_file() else "single_attempt_no_child"
                write(RUN/"watch-end.json", dict(disposition=state, attempts=1, status=code, exports=replacements,
                      observed_deferral=event, finished_unix_ns=time_ns()))
                return
        write(RUN/"watch-end.json", dict(disposition="no_new_storage_deferral", attempts=0, exports=replacements,
                                        finished_unix_ns=time_ns()))
    finally:
        os.close(fd)


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    observe()
