"""One bounded, nonblocking saved-child opportunity between official workers."""

import runpy
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep, time_ns

from field_crossover_admission_watch import recent_deferral

QUIET = Path("/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/guarded_stage_idle.py")
QUIET_PIN = "a4d2575cb5ec65014f6415ca61adf8423dd1c1ded84d56af06f38cb13b1b5c56"
WATCH_S = 15
FRESH_NS = 3_000_000_000


def device_stats(lines):
    required = {"/srv/bulk", "/srv/postgres-nvme"}
    mounts = {}
    for line in lines:
        _, _, device, _, path, *_ = line.split()
        if path in required:
            if path in mounts:
                raise ValueError("Expected a single device for each live storage mount")
            mounts[path] = Path("/sys/dev/block") / device / "stat"
    if mounts.keys() != required:
        raise ValueError("Live storage devices changed")
    return mounts


def confirm_quiet(event, deadline, quiet, devices):
    guards = {name: quiet["QuietInterval"]() for name in devices}
    quiet_deadline = min(deadline, monotonic()+2*quiet["MIN_QUIET_S"])
    while monotonic() < quiet_deadline and time_ns()-event["unix_ns"] <= FRESH_NS:
        states = {name: quiet["sample"](path, monotonic) for name,path in devices.items()}
        ready = [guards[name].observe(state) for name,state in states.items()]
        if all(ready) and monotonic() < deadline and time_ns()-event["unix_ns"] <= FRESH_NS:
            return dict(deferral=event, quiet={
                name: dict(asdict(state), queue_mean=guards[name].queue_mean,
                           interval_full_pct=guards[name].current_full)
                for name,state in states.items()})
        sleep(min(quiet["POLL_S"], max(0, quiet_deadline-monotonic())))
    raise ValueError("No qualifying quiet interval within the fresh official deferral")


def watch(root, plan_pin, *, campaign, launch, record):
    used = ("watch.json", "worker.stdout", "prediction-seal.json")
    if any((root/name).exists() for name in used):
        raise ValueError("The single joint opportunity is already used")
    if sha256(QUIET.read_bytes()).hexdigest() != QUIET_PIN:
        raise ValueError("Official quiet guard changed")
    quiet = runpy.run_path(str(QUIET))
    devices = device_stats(Path("/proc/self/mountinfo").read_text().splitlines())
    export = campaign/"rows.jsonl"
    previous = export.stat().st_ino
    started, deadline = time_ns(), monotonic()+WATCH_S
    while monotonic() < deadline:
        current = export.stat().st_ino
        if current != previous:
            previous = current
            event = recent_deferral(campaign, started, time_ns())
            if event is not None and time_ns()-event["unix_ns"] <= FRESH_NS:
                def admitted(gate=event):
                    return confirm_quiet(gate, deadline, quiet, devices)

                try:
                    launch(admitted)
                except (OSError, ValueError) as error:
                    result = dict(status="single_attempt_blocked_or_failed", reason=str(error))
                else:
                    result = dict(status="prediction_sealed")
                return record(root/"watch.json", dict(result, event=event, watch_s=WATCH_S,
                            started_ns=started, finished_ns=time_ns(), plan_sha256=plan_pin))
        sleep(min(.10, max(0, deadline-monotonic())))
    return record(root/"watch.json", dict(status="no_fresh_official_storage_deferral",
                  watch_s=WATCH_S, started_ns=started, finished_ns=time_ns(), plan_sha256=plan_pin))
