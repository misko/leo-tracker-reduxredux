"""One passive admission opportunity for the frozen original DS30-0049 prefix."""

import argparse
from collections import Counter, deque
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

from . import empty_lane_directed_replay as replay
from guarded_stage_idle import FULL_LIMIT, QUEUE_LIMIT


TIMEOUT_S = 18
FIELD_SLEEP_S = 30
WATCH_S = 300
SAMPLE_S = 1.
ROLLING_S = 2.


def lock_present(path, locks):
    stat = path.stat()
    target = os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino
    for line in locks.splitlines():
        for field in line.split():
            parts = field.split(":")
            if len(parts) == 3 and (int(parts[0], 16), int(parts[1], 16), int(parts[2])) == target:
                return True
    return False


def rolling_window(previous, current):
    if not previous.keys() or previous.keys() != current.keys():
        return None
    result = {}
    for name, old in previous.items():
        new = current[name]
        span = new["at"] - old["at"]
        if not ROLLING_S <= span <= ROLLING_S + 2 * SAMPLE_S:
            return None
        result[name] = dict(span_s=span, queue_mean=(new["weighted_ms"] - old["weighted_ms"]) / (span * 1000),
                            full_pct=(new["full_total_us"] - old["full_total_us"]) / (span * 10_000))
    return result


def eligible(event, deferred, storage, busy, rolling):
    if not deferred or event["age_s"] >= 4 or FIELD_SLEEP_S - event["age_s"] < TIMEOUT_S + 6:
        return "no-fresh-field-sleep"
    if busy:
        return "shared-lease-present"
    if any(row["full_avg10"] >= FULL_LIMIT or row["in_flight"] > QUEUE_LIMIT for row in storage.values()):
        return "storage-pressure"
    if rolling is None:
        return "rolling-window-unavailable"
    if any(not (0 <= row["queue_mean"] <= QUEUE_LIMIT and 0 <= row["full_pct"] < FULL_LIMIT)
           for row in rolling.values()):
        return "rolling-storage-pressure"
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
    samples = deque(maxlen=4)
    counts, last_refusals = Counter(), {}
    start = monotonic()
    while monotonic() - start < WATCH_S:
        event, deferred = replay.prefix.occupied()
        storage = storage_sample()
        previous, rolling = None, None
        for candidate in reversed(samples):
            rolling = rolling_window(candidate, storage)
            if rolling is not None:
                previous = candidate
                break
        samples.append(storage)
        busy = deferred and lock_present(replay.LOCK, Path("/proc/locks").read_text())
        observation = dict(event=event, storage=storage, earlier_storage=previous, rolling=rolling, lease_busy=busy)
        reason = eligible(event, deferred, storage, busy, rolling)
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
                                    **observation, residency=pages, polls=dict(counts), last_refusals=last_refusals,
                                    elapsed_s=monotonic()-start, stdout=result.stdout, stderr=result.stderr))
                return result.returncode
        else:
            counts[reason] += 1
            last_refusals[reason] = observation
        sleep(SAMPLE_S)
    replay.prefix.write(output / "watch.json", dict(launched=False, reason="readiness-window-expired",
                        **observation, polls=dict(counts), last_refusals=last_refusals, elapsed_s=monotonic()-start))
    return replay.ABSTAIN_EXIT


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("plan_sha256")
    args = parser.parse_args()
    args.output.mkdir(mode=0o750)
    sys.exit(wait(args.output, args.plan, args.plan_sha256))
