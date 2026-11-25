"""Freeze and perform the one zero-backing-read DS30-0208 capture."""

import argparse
import ctypes
import errno
import gzip
import json
import os
import platform
import pwd
import resource
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from time import monotonic
from unittest.mock import patch

import guarded_cfo_0016_stage as copier
from combined_second_original import CAMPAIGN, NVME, PLAN_PIN, checked_doc, extent, recording_roster
from combined_second_stage import SOURCE, LiveGap, guarded_sample
from combined_small_panel import DRIVER, DRIVER_PIN, LOCK, check, digest, write
from ds30_paired_inputs import AUDIT, MANIFEST
from guarded_stage_idle import IdleAdmission, IdleWindowExpired, sample

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CASE = "DS30-0208"
ROOT = Path("/srv/postgres-nvme/leo-ds30-0208-cache-only")
MAX_BYTES = 4_154_415_556
RATE = 16 * 1024**2
BLOCK = 1024**2
RWF_NOWAIT = 0x8
CACHESTAT_X86_64 = 451
SOURCES = (
    "combined_cache_0208.py",
    "combined_second_original.py",
    "combined_second_stage.py",
    "combined_small_panel.py",
    "guarded_cfo_0016_stage.py",
    "guarded_stage_checkpoint.py",
    "guarded_stage_idle.py",
    "field_crossover_admission_watch.py",
)


def git_object(name, encoded_pin, *, compressed=False):
    body = subprocess.check_output(
        ["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), "show", "HEAD:" + name]
    )
    decoded = gzip.decompress(body) if compressed else body
    if digest(decoded) != encoded_pin.removeprefix("sha256:"):
        raise ValueError("The signed accession inputs changed")
    return json.loads(decoded)


def enrollment():
    from ds30_paired_inputs import historical_input

    plan = checked_doc(CAMPAIGN / "plan.json", PLAN_PIN)
    order = plan["smoke"] + [r["case"] for r in plan["cases"] if r["case"] not in plan["smoke"]]
    (row,) = (item for item in plan["cases"] if item["case"] == CASE)
    if order.index(CASE) + 1 != 96 or row["window_count"] != 3359:
        raise ValueError("The exact prospective medium case changed")
    all_members = git_object(
        "reports/2026_11_20_ds30_fast/dataset/manifest.json.gz", MANIFEST, compressed=True
    )
    (member,) = (item for item in all_members["members"] if item["dataset_label"] == CASE)
    audit = git_object("reports/2026_11_21_ds30_full/input-audit.json", AUDIT)
    offer = checked_doc(CAMPAIGN / "offer.json", plan["offered_region_sha256"])
    history = historical_input(row, member, audit["bindings"][CASE], offer)
    original = Path(row["recording"])
    manifests = [
        dict(path=str(Path(item["path"]).parent), manifest_digest=item["sha256"])
        for item in member["raw_recording"]["segments"]
    ]
    raw, segments = recording_roster({"segments": manifests}, original)
    for item in raw:
        item["target"] = str(Path("recording") / original.name / item["relative"])
    archive = Path(history["archive"])
    causal = []
    for path in sorted((archive / "archive/space-track").glob("*.tle")):
        epoch, sha = path.stem.split("-", 1)
        if int(epoch) >= history["expected"]["causal_cutoff_utc_ns"]:
            raise ValueError("The exact archived view contains a future body")
        causal.append(
            dict(
                path=str(path),
                target=str(Path("tle/archive/space-track") / path.name),
                size=extent(path),
                sha256="sha256:" + sha,
                kind="causal",
            )
        )
    files = raw + causal
    if (
        len(segments) != 7
        or len(causal) != 51
        or len(files) != 164
        or sum(item["size"] for item in files) != MAX_BYTES
        or any(Path(item["path"]).stat().st_dev != os.makedev(252, 5) for item in files)
    ):
        raise ValueError("The one enrolled source differs from its signed extent")
    return dict(
        case=CASE,
        rank=96,
        files=files,
        bytes=MAX_BYTES,
        expected=history["expected"],
        offered_region=offer,
        offer_sha256=plan["offered_region_sha256"],
        expected_admitted=history["expected_admitted"],
        official_plan_sha256=PLAN_PIN,
        sources={name: digest((HERE / name).read_bytes()) for name in SOURCES},
    )


class CacheRange(ctypes.Structure):
    _fields_ = [("off", ctypes.c_uint64), ("length", ctypes.c_uint64)]


class IOVec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("length", ctypes.c_size_t)]


LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.syscall.restype = ctypes.c_long
LIBC.preadv2.argtypes = (ctypes.c_int, ctypes.POINTER(IOVec), ctypes.c_int, ctypes.c_int64, ctypes.c_int)
LIBC.preadv2.restype = ctypes.c_ssize_t


def read_nowait(stream, amount):
    """Use the libc binding when the frozen interpreter has no flags-enabled syscall wrapper."""
    data = bytearray(amount)
    exported = (ctypes.c_char * amount).from_buffer(data)
    iov = IOVec(ctypes.addressof(exported), amount)
    count = LIBC.preadv2(stream.fileno(), ctypes.byref(iov), 1, stream.tell(), RWF_NOWAIT)
    if count < 0:
        failure = ctypes.get_errno()
        raise OSError(failure, os.strerror(failure))
    stream.seek(count, os.SEEK_CUR)
    return data if count == amount else data[:count]


def range_pages(stream, amount):
    """Linux x86-64 cachestat on the actual source descriptor, without mapping or faulting pages."""
    if platform.machine() != "x86_64":
        raise OSError(errno.ENOSYS, "The enrolled Linux cachestat syscall is unavailable")
    counters = (ctypes.c_uint64 * 5)()
    interval = CacheRange(stream.tell(), amount)
    if LIBC.syscall(CACHESTAT_X86_64, stream.fileno(), ctypes.byref(interval), ctypes.byref(counters), 0) != 0:
        failure = ctypes.get_errno()
        raise OSError(failure, os.strerror(failure))
    return counters[0]


def read_counters():
    return resource.getrusage(resource.RUSAGE_THREAD).ru_inblock


@dataclass
class SourceReads:
    range_checks: int = 0
    range_checked_bytes: int = 0
    privileged_census_only_ranges: int = 0
    privileged_census_only_bytes: int = 0
    source_reads_attempted: int = 0
    source_reads_metered: int = 0
    source_bytes_returned: int = 0
    source_read_input_blocks: int = 0
    source_read_bytes_charged: int = 0
    refused_interval: dict | None = None

    def read(self, item, stream, amount):
        interval = dict(target=item["target"], offset=stream.tell(), requested_bytes=amount)
        page = os.sysconf("SC_PAGE_SIZE")
        try:
            if not 0 < amount <= BLOCK or interval["offset"] % page:
                raise ValueError("The cache capture requires a bounded page-aligned source interval")
            try:
                cached = range_pages(stream, amount)
            except OSError as failure:
                if (failure.errno != errno.EPERM or item["kind"] != "causal"
                        or os.fstat(stream.fileno()).st_uid != 0):
                    raise
                interval["cache_preflight"] = "privileged_roster_only"
                self.privileged_census_only_ranges += 1
                self.privileged_census_only_bytes += amount
            else:
                required = (amount + page - 1) // page
                interval.update(cache_preflight="descriptor_cachestat", cached_pages=cached, required_pages=required)
                self.range_checks += 1
                if cached != required:
                    raise OSError(errno.EAGAIN, "The immediate cache range has missing pages")
                self.range_checked_bytes += amount
            return zero_io_read(stream, amount, self, interval)
        except (OSError, ValueError) as failure:
            self.refused_interval = interval | dict(reason=str(failure))
            raise

    def summary(self, state, expected):
        return vars(self) | dict(zero_input_blocks_per_admitted_source_read=(
            state == "complete" and self.source_reads_attempted == self.source_reads_metered > 0
            and self.range_checked_bytes + self.privileged_census_only_bytes == self.source_bytes_returned == expected
            and self.source_read_input_blocks == 0 and self.refused_interval is None
            and self.source_read_bytes_charged == 0
        ))


def zero_io_read(stream, amount, reads, interval):
    before = read_counters()
    data = b""
    reads.source_reads_attempted += 1
    try:
        data = read_nowait(stream, amount)
    except OSError as failure:
        interval["nowait_errno"] = failure.errno
        raise
    finally:
        interval["returned_bytes"] = len(data)
        reads.source_bytes_returned += len(data)
        blocks = read_counters() - before
        if blocks < 0:
            raise OSError("Source thread accounting counters regressed")
        charged = 512 * blocks
        reads.source_reads_metered += 1
        reads.source_read_input_blocks += blocks
        reads.source_read_bytes_charged += charged
        interval.update(input_blocks=blocks, read_bytes_charged=charged)
    if len(data) != amount or blocks or charged:
        raise OSError("The cache-only source interval was not a complete zero-input read")
    return data


def ready_sample(pid, now, gap, destination):
    original = guarded_sample(pid, now, gap)
    target = sample(destination, now)
    return replace(
        original,
        in_flight=3 if original.in_flight or target.in_flight else 0,
        weighted_ms=original.weighted_ms + target.weighted_ms,
    )


def capture(book, gate, pid):
    if (
        os.geteuid() != pwd.getpwnam("leo").pw_uid
        or os.sched_getaffinity(0) != {3}
        or os.getpriority(os.PRIO_PROCESS, 0) < 15
        or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "idle"
    ):
        raise ValueError("Cache capture requires the recording account, CPU 3 and idle I/O")
    if not gate["all_pages_resident"] or book["case"] != CASE or book["bytes"] != MAX_BYTES:
        raise ValueError("The exact cache-only source was not admitted")
    if set(book["sources"]) != set(SOURCES):
        raise ValueError("The frozen cache-only source closure changed")
    for name, pin in book["sources"].items():
        check(HERE / name, pin)
    device = ROOT.stat().st_dev
    if ROOT.resolve(strict=True) != ROOT or device != NVME.stat().st_dev:
        raise ValueError("The detached destination is not the independent NVMe workspace")
    destination = Path(f"/sys/dev/block/{os.major(device)}:{os.minor(device)}/stat")
    check(DRIVER, DRIVER_PIN)
    if (ROOT / "cache-capture-intent.json").exists():
        raise ValueError("The one cache-only prospective recording has already been attempted")
    write(
        ROOT / "cache-capture-intent.json",
        dict(
            case=CASE,
            pair_sha256=gate["pair_sha256"],
            cache_query_sha256=gate["resident_roster_sha256"],
        ),
    )
    start = monotonic()
    shared = LiveGap()
    reads = SourceReads()
    with (
        LOCK.open("rb") as lock,
        patch.object(copier, "RATE", RATE),
        patch.object(copier, "BLOCK", BLOCK),
    ):
        pace = copier.Pacing(ROOT, MAX_BYTES, 0, idle=True, device=SOURCE, deadline=start + 1200)
        admission = IdleAdmission(
            SOURCE,
            start + 1200,
            pace.record,
            now=monotonic,
            observe=lambda _, now: ready_sample(pid, now, shared, destination),
        )
        state, reason = "complete", None
        completed = []
        try:
            for item in book["files"]:
                source, target = Path(item["path"]), ROOT / item["target"]
                extent(source, item["size"])
                if not target.is_relative_to(ROOT) or target.resolve() != target:
                    raise ValueError("Detached cache copy target escapes its private workspace")
                target.parent.mkdir(parents=True, exist_ok=True)
                copier.copy_member(
                    source,
                    target,
                    item["size"],
                    item["sha256"],
                    lock,
                    pace,
                    admission=admission,
                    required_device=os.makedev(252, 5),
                    read_bytes=lambda stream, amount: reads.read(item, stream, amount),
                )
                completed.append(item["target"])
        except (IdleWindowExpired, OSError, RuntimeError, ValueError) as problem:
            state, reason = "refused", str(problem)
    result = dict(
        case=CASE,
        state=state,
        reason=reason,
        elapsed_s=monotonic() - start,
        copied_bytes=pace.copied,
        completed=completed,
        leases=admission.reads,
        origin="strict_RWF_NOWAIT",
        pair_sha256=gate["pair_sha256"],
        authority=gate["authority"],
    ) | reads.summary(state, MAX_BYTES)
    print(write(ROOT / "cache-capture-result.json", result))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("freeze", "capture"))
    cli.add_argument("--gate", type=Path)
    cli.add_argument("--gate-pin")
    cli.add_argument("--book", type=Path)
    cli.add_argument("--book-pin")
    cli.add_argument("--driver-pid", type=int)
    args = cli.parse_args()
    if args.mode == "freeze":
        print(json.dumps(enrollment(), sort_keys=True, indent=2, allow_nan=False))
    elif all((args.gate, args.gate_pin, args.book, args.book_pin, args.driver_pid)):
        capture(
            checked_doc(args.book, args.book_pin),
            checked_doc(args.gate, args.gate_pin),
            args.driver_pid,
        )
    else:
        cli.error("The privileged cache gate must supply the exact original closure")
