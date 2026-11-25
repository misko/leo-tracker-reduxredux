"""Checkpoint one authenticated DS30-0339 copy on the independent NVMe volume."""

import argparse
import json
import os
import pwd
import resource
import subprocess
from dataclasses import replace
from pathlib import Path
from time import monotonic, sleep, time_ns
from unittest.mock import patch

import guarded_cfo_0016_stage as copier
from combined_second_original import CAMPAIGN, CASE, NVME, RATE, cache, enrollment
from combined_small_panel import DRIVER, DRIVER_PIN, LOCK, check, write
from field_crossover_admission_watch import recent_deferral
from guarded_stage_checkpoint import Extent, checked_local, staging_lock, verified_extents
from guarded_stage_idle import IdleAdmission, IdleWindowExpired, QuietInterval, sample

ROOT = NVME / "leo-ds30-0339-second-original"
CAUSAL_ROOT = Path("/dev/shm/leo-v3-0339-causal-original01")
SOURCE = Path("/sys/dev/block/252:5/stat")
RAID = Path("/sys/dev/block/9:127/stat")
BLOCK = 1024**2
MAX_GAP_NS = 12_000_000_000


def official_active(pid):
    proc = Path("/proc") / str(pid)
    cmd = (proc / "cmdline").read_bytes().split(b"\0")
    if not any(
        a == os.fsencode(DRIVER) and b == b"run" for a, b in zip(cmd, cmd[1:], strict=False)
    ):
        raise ValueError("Expected the pinned live official controller")
    return bool((proc / "task" / str(pid) / "children").read_text().strip())


class LiveGap:
    """Use only the early part of a genuine published official retry window."""

    def __init__(self, campaign=CAMPAIGN, *, clock=time_ns, observe=recent_deferral):
        self.campaign, self.clock, self.observe = campaign, clock, observe
        self.inode, self.event = None, None

    def available(self):
        current = (self.campaign / "rows.jsonl").stat().st_ino
        now = self.clock()
        if current != self.inode:
            self.inode = current
            self.event = self.observe(self.campaign, now - MAX_GAP_NS, now)
        return self.event is not None and 0 <= now - self.event["unix_ns"] <= MAX_GAP_NS


def guarded_sample(pid, now, gap=None):
    source, raid = sample(SOURCE, now), sample(RAID, now)
    busy = official_active(pid) or source.in_flight > 0 or raid.in_flight > 0
    busy = busy or (gap is not None and not gap.available())
    return replace(
        source, in_flight=3 if busy else 0, weighted_ms=source.weighted_ms + raid.weighted_ms
    )


def inspect_idle(pid):
    guard, admitted = QuietInterval(), 0
    gap = LiveGap()
    states = []
    for _ in range(13):
        state = guarded_sample(pid, monotonic, gap)
        states.append(state.__dict__)
        admitted += guard.observe(state)
        sleep(0.25)
    return dict(samples=states, quiet_admissions=admitted)


def read_nowait(stream, amount):
    """A cache miss or unsupported read aborts this transaction before fallback."""
    data = bytearray(amount)
    count = os.preadv(stream.fileno(), [data], stream.tell(), getattr(os, "RWF_NOWAIT", 0x8))
    stream.seek(count, os.SEEK_CUR)
    return data[:count]


def extent_for(row):
    return Extent(Path(row["relative"]), row["size"], row["sha256"])


def copy_group(destination, rows, checkpoint, lock, pacing, admission):
    active = json.loads(checkpoint.read_bytes()) if checkpoint.exists() else None
    complete, partial = verified_extents(destination, list(map(extent_for, rows)), active)
    for row in rows:
        item = extent_for(row)
        if item.relative in complete:
            continue
        source, target = Path(row["path"]), destination / item.relative
        target.parent.mkdir(parents=True, exist_ok=True)
        (pages,) = cache([source])
        read_bytes = read_nowait if pages["res"] >= pages["size"] else None
        resume = partial if partial is not None and partial.extent == item else None
        copier.copy_member(
            source,
            target,
            item.size,
            item.sha256,
            lock,
            pacing,
            partial=resume,
            journal=checkpoint,
            admission=admission,
            required_device=os.makedev(252, 5),
            read_bytes=read_bytes,
        )


def stage(pid, budget):
    if (
        os.geteuid() != pwd.getpwnam("leo").pw_uid
        or os.sched_getaffinity(0) != {3}
        or os.getpriority(os.PRIO_PROCESS, 0) < 15
        or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "idle"
    ):
        raise ValueError("Stage only as the recording account on idle-I/O CPU 3")
    if (
        not 0 < budget <= 660
        or ROOT.resolve(strict=True) != ROOT
        or ROOT.stat().st_dev != NVME.stat().st_dev
    ):
        raise ValueError("Require one private NVMe staging root and bounded window")
    check(DRIVER, DRIVER_PIN)
    book = enrollment()
    original = Path(book["authority"]["recording"])
    if os.major(original.stat().st_dev) != 252 or os.minor(original.stat().st_dev) != 5:
        raise ValueError("The physical source-device guard no longer names the source")
    if (ROOT / "verified-stage.json").exists():
        return dict(state="already_sealed")
    if (
        CAUSAL_ROOT.resolve() != CAUSAL_ROOT
        or CAUSAL_ROOT.exists()
        and CAUSAL_ROOT.stat().st_dev != Path("/dev/shm").stat().st_dev
    ):
        raise ValueError("Require the direct local causal stage on the donor filesystem")
    with (
        staging_lock(ROOT / "copy.lock"),
        LOCK.open("rb") as lock,
        patch.object(copier, "RATE", RATE),
        patch.object(copier, "BLOCK", BLOCK),
    ):
        start = monotonic()
        cpu0 = resource.getrusage(resource.RUSAGE_SELF)
        causal = CAUSAL_ROOT / "tle/archive"
        (causal / "space-track").mkdir(parents=True, exist_ok=True)
        pace = copier.Pacing(
            ROOT, book["new_backing_bytes"], 0, idle=True, device=SOURCE, deadline=start + budget
        )
        gap = LiveGap()
        admission = IdleAdmission(
            SOURCE,
            start + budget,
            pace.record,
            now=monotonic,
            observe=lambda _, now: guarded_sample(pid, now, gap),
        )
        state = "window_expired"
        try:
            with patch.object(copier, "RATE", RATE), patch.object(copier, "BLOCK", BLOCK):
                data = sorted(
                    book["files"], key=lambda row: (row["kind"] == "payload", row["relative"])
                )
                copy_group(
                    ROOT / original.name,
                    data,
                    ROOT / "recording-checkpoint.json",
                    lock,
                    pace,
                    admission,
                )
                missing = [
                    dict(row, relative="space-track/" + row["name"])
                    for row in book["causal"]
                    if not row["donor"]
                ]
                copy_group(causal, missing, ROOT / "archive-checkpoint.json", lock, pace, admission)
                for row in book["causal"]:
                    if row["donor"]:
                        donor, target = Path(row["donor"]), causal / "space-track" / row["name"]
                        checked_local(donor, row["size"], row["sha256"])
                        if not target.exists():
                            os.link(donor, target)
                        elif target.stat().st_ino != donor.stat().st_ino:
                            raise ValueError("The local staged causal link changed")
            state = "complete"
        except IdleWindowExpired:
            pass
        except (BlockingIOError, NotImplementedError, OSError) as problem:
            state = f"source_read_stopped: {problem}"
        usage = resource.getrusage(resource.RUSAGE_SELF)
        receipt = dict(
            case=CASE,
            state=state,
            wall_s=monotonic() - start,
            source_bytes_copied=pace.copied,
            source_io_blocks=usage.ru_inblock - cpu0.ru_inblock,
            admitted_read_chunks=admission.reads,
            shared_wait_s=admission.wait_s,
            allowed_new_bytes=book["new_backing_bytes"],
            recording=str(ROOT / original.name),
            archive=str(causal.parent),
            authority=book["authority"],
        )
        write(ROOT / f"copy-result-{os.getpid()}.json", receipt)
        if state == "complete":
            write(ROOT / "verified-stage.json", receipt)
        return receipt


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("preflight", "copy"))
    cli.add_argument("--driver-pid", type=int, required=True)
    cli.add_argument("--seconds", type=float, default=660)
    args = cli.parse_args()
    result = (
        inspect_idle(args.driver_pid)
        if args.mode == "preflight"
        else stage(args.driver_pid, args.seconds)
    )
    print(json.dumps(result, sort_keys=True))
