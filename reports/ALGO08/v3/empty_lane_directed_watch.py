"""One passive admission opportunity for the frozen original DS30-0049 prefix."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

from . import empty_lane_directed_replay as replay


TIMEOUT_S = 18
FIELD_SLEEP_S = 30


def lock_present(path, locks):
    stat = path.stat()
    target = os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino
    for line in locks.splitlines():
        for field in line.split():
            parts = field.split(":")
            if len(parts) == 3 and (int(parts[0], 16), int(parts[1], 16), int(parts[2])) == target:
                return True
    return False


def eligible(event, deferred, storage, busy):
    if not deferred or event["age_s"] >= 4 or FIELD_SLEEP_S - event["age_s"] < TIMEOUT_S + 6:
        return "no-fresh-field-sleep"
    if busy:
        return "shared-lease-present"
    if any(row["full_avg10"] >= 20. or row["in_flight"] > 2 for row in storage.values()):
        return "storage-pressure"
    return None


def wait(output, plan, pin):
    from ds30_paired_evaluation import storage_sample
    from visit_frame_raw_0016 import resident

    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Use the same low-priority CPU2 environment as the timed child")
    inputs = replay.prefix.read(plan, pin)
    if inputs["source_sha256"] != replay.tag(Path(replay.__file__)):
        raise ValueError("The passive watcher requires the unchanged frozen worker")
    # The ordinary driver sleeps for 30 seconds after a failed quiet-window check.
    # Watch only metadata, and leave time for it to resume even if the child reaches its bound.
    counts = Counter()
    start = monotonic()
    while monotonic() - start < 180:
        event, deferred = replay.prefix.occupied()
        storage = storage_sample()
        busy = lock_present(replay.LOCK, Path("/proc/locks").read_text())
        reason = eligible(event, deferred, storage, busy)
        if reason is None:
            try:
                pages = resident(inputs["original_source"]["files"])
            except ValueError:
                counts["private-input-not-resident"] += 1
            else:
                command = ["/usr/bin/time", "-f", "elapsed=%e user=%U system=%S rss_kib=%M input_blocks=%I exit=%x",
                           "-o", str(output / "process.txt"), "/usr/bin/timeout", "-k", "1s", f"{TIMEOUT_S}s",
                           sys.executable, "-B", "-m", "reports.ALGO08.v3.empty_lane_directed_replay", "run",
                           str(output / "waveforms.json"), "--plan", str(plan), "--plan-sha256", pin]
                result = subprocess.run(command, capture_output=True, text=True)
                replay.prefix.write(output / "watch.json", dict(launched=True, exit_code=result.returncode,
                                    event=event, storage=storage, residency=pages, polls=dict(counts),
                                    elapsed_s=monotonic()-start, stdout=result.stdout, stderr=result.stderr))
                return result.returncode
        else:
            counts[reason] += 1
        sleep(2.)
    replay.prefix.write(output / "watch.json", dict(launched=False, reason="readiness-window-expired",
                        event=event, storage=storage, polls=dict(counts), elapsed_s=monotonic()-start))
    return replay.ABSTAIN_EXIT


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("plan_sha256")
    args = parser.parse_args()
    args.output.mkdir(mode=0o750)
    sys.exit(wait(args.output, args.plan, args.plan_sha256))
