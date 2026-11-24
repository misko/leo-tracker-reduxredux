"""Stage the complete signed physical DS30-0016 once at a controlled device rate."""

import argparse
from contextlib import contextmanager
import fcntl
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import stat
import sys
from time import perf_counter, process_time, sleep


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from raw_0016_best_trial import ORIGINAL
from short_raw_0180 import BULK, enrollment
from guarded_stage_checkpoint import Extent, checkpoint, checked_local, identity, staging_lock, verified_extents, write_checkpoint


RECORDING = BULK / "leo/fast-scan-recordings/fast8-auto-20261113-112146-b04f5461-1-lower"
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
STAGING_LOCK = Path("/dev/shm/leo-v3-guarded-selective-0016-staging.lock")
STOPPED_RECEIPT = HERE / "measurements/guarded-cfo-0016-stopped-stage.json.gz"
STOPPED_SHA = "8271a2d880a00db4e118a536df20c126ade2ed5e80a69fa79b0e67760933c3d1"
STOPPED_ROOT = Path("/dev/shm/leo-v3-guarded-selective-0016-stage01")
MB = 1024**2
BLOCK = MB
RATE = 2 * MB
MEMORY_MIN = 4 * 1024**3
PAYLOAD, INDEX, MANIFEST = "payload", "index", "manifest"
COPY_ORDER = (MANIFEST, INDEX, PAYLOAD)


def signed_members(root=RECORDING):
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.short_window import ShortWindowReader

    workload = ORIGINAL.workload
    signed, request = enrollment(workload)
    case = signed["case"]
    session, digest, inventory = FastScanStore(Path("/dev/shm")).inventory(root, verify_windows=False)
    if ((session, digest, inventory["window_count"]) != (case["session_id"], ORIGINAL.inventory, workload.windows)
            or signed["orbit_cutoff_ns"] != ORIGINAL.cutoff_ns or case["valid_visits"] != ORIGINAL.admitted
            or len(inventory["segments"]) != 2):
        raise ValueError("Original recording binding changed")
    files = {PAYLOAD: [], INDEX: [], MANIFEST: []}
    for observed, expected in zip(inventory["segments"], case["recording"]["segments"], strict=True):
        segment = Path(observed["path"])
        manifest = segment / "manifest.json"
        reader = ShortWindowReader(segment)
        if (manifest != BULK / expected["path"] or reader.manifest_sha256 != "sha256:" + expected["sha256"]
                or reader.manifest_sha256 != observed["manifest_digest"]):
            raise ValueError("Signed original segment or order changed")
        files[MANIFEST].append((manifest, manifest.stat().st_size, reader.manifest_sha256))
        for chunk in reader.manifest.chunks:
            files[INDEX].append((segment / chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256))
            files[PAYLOAD].append((segment / chunk.payload_relative_path, chunk.compressed_bytes,
                                   chunk.compressed_sha256))
    extents = {kind: sum(record[1] for record in rows) for kind, rows in files.items()}
    all_rows = [row for rows in files.values() for row in rows]
    if (len(files[INDEX]) != len(files[PAYLOAD]) or len(files[PAYLOAD]) != ORIGINAL.members
            or extents[PAYLOAD] != workload.compressed_bytes or sum(extents.values()) > workload.raw_limit
            or len({path for path, _, _ in all_rows}) != len(all_rows)
            or any(path.resolve(strict=True) != path or path.stat().st_size != size for path, size, _ in all_rows)):
        raise ValueError("Original payload or sidecar extent changed")
    return signed, request, files, extents


def cache_states(files):
    from empty_bootstrap import checked
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, cache_residency

    checked(CACHE_LIB, CACHE_SHA)
    query = cache_residency.load_query(CACHE_LIB)
    page = os.sysconf("SC_PAGE_SIZE")
    scopes = {kind: cache_residency.cache_snapshot([(p.parent, p.name, size) for p,size,_ in files[kind]], page, query)
              for kind in (PAYLOAD, INDEX)}
    if any(scope["unavailable"] or scope["members"] != scope["observed_members"] for scope in scopes.values()):
        raise ValueError("Could not observe the complete signed payload/index residency")
    return scopes


def fully_resident(scopes):
    return all(0 < state["cached_pages"] == state["observed_file_pages"] for state in scopes.values())


@contextmanager
def source_slot(lock):
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)


def reads(stat_file):
    values = [int(value) for value in stat_file.read_text().split()]
    return values[0], values[3]


def average_read_ms(before, after):
    completed, millis = (current - earlier for earlier,current in zip(before, after, strict=True))
    if completed < 0 or millis < 0:
        raise ValueError("Block device counters regressed")
    return millis / completed if completed >= 8 else None


class Pacing:
    def __init__(self, root, total, reused):
        dev = RECORDING.stat().st_dev
        self.device = Path(f"/sys/dev/block/{os.major(dev)}:{os.minor(dev)}/stat")
        self.total, self.copied, self.wait_s, self.slowest = total, reused, 0.0, 0.0
        self.start, self.sample_time = perf_counter(), perf_counter()
        self.sample, self.high, self.pauses = reads(self.device), 0, 0
        sleep(2)
        measured = reads(self.device)
        self.baseline = average_read_ms(self.sample, measured)
        self.sample, self.sample_time = measured, perf_counter()
        self.limit = max(50.0, 2 * (self.baseline or 0) + 10)
        self.log = root / "copy-progress.jsonl"
        self.record(event="begin", device=str(self.device), baseline_read_ms=self.baseline,
                    rate_limit_bytes_s=RATE, read_stall_limit_ms=self.limit, reused_verified_bytes=reused)

    def record(self, **details):
        elapsed = perf_counter() - self.start
        event = dict(copied=self.copied, total=self.total, elapsed_s=elapsed, shared_lock_wait_s=self.wait_s,
                     min_remaining_s=(self.total-self.copied)/RATE, slowest_block_read_s=self.slowest,
                     io_pressure=Path("/proc/pressure/io").read_text(), **details)
        with self.log.open("a") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
        print(json.dumps(event, sort_keys=True), flush=True)

    def progress(self, read_s, count):
        self.copied += count
        self.slowest = max(self.slowest, read_s)
        now = perf_counter()
        if now - self.sample_time < 10 and read_s < .75:
            return
        observed = reads(self.device)
        mean = average_read_ms(self.sample, observed)
        self.sample, self.sample_time = observed, now
        self.high = self.high + 1 if mean is not None and mean > self.limit else 0
        available = next(line for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:"))
        if int(available.split()[1]) * 1024 < MEMORY_MIN:
            self.record(event="abort", reason="host_memory_need", read_await_ms=mean)
            raise RuntimeError("Host needs available memory")
        self.record(event="progress", read_await_ms=mean)
        if self.high < 2 and read_s < .75:
            return
        if self.pauses == 2:
            self.record(event="abort", reason="persistent_read_stalls", read_await_ms=mean)
            raise RuntimeError("Read stalls persisted after two pauses")
        self.pauses += 1
        self.high = 0
        self.record(event="pause", reason="device_read_stalls", read_await_ms=mean)
        sleep(20)
        self.sample, self.sample_time = reads(self.device), perf_counter()


def copy_member(source, target, size, digest, lock, pacing, *, partial=None, journal=None):
    completed = partial.offset if partial else 0
    checksum = partial.checksum.copy() if partial else sha256()
    digest = "sha256:" + digest.removeprefix("sha256:")
    extent = Extent(Path(target.parent.name) / target.name, size, digest)
    if partial and partial.extent != extent:
        raise ValueError("The recovered prefix belongs to a different signed extent")
    with source.open("rb", buffering=0) as entry:
        incoming = os.fstat(entry.fileno())
        if not stat.S_ISREG(incoming.st_mode) or incoming.st_size != size:
            raise ValueError("Original member is not the expected bounded regular file")
        member_identity = identity(incoming)
        if partial and partial.source_identity is not None and partial.source_identity != member_identity:
            raise ValueError("Original source identity changed since the sealed checkpoint")
        entry.seek(completed)
        os.posix_fadvise(entry.fileno(), completed, size - completed, os.POSIX_FADV_RANDOM)
        if journal is not None:
            write_checkpoint(journal, checkpoint(extent, member_identity, [(completed, "sha256:" + checksum.hexdigest())]))
        mode = "r+b" if completed or partial and target.exists() else "xb"
        with target.open(mode, buffering=0) as staged:
            if os.fstat(staged.fileno()).st_size != completed:
                raise ValueError("Checked local prefix changed before resume")
            staged.seek(completed)
            while completed < size:
                waiting = perf_counter()
                with source_slot(lock):
                    beginning = perf_counter()
                    pacing.wait_s += beginning - waiting
                    data = entry.read(min(BLOCK, size - completed))
                    read_s = perf_counter() - beginning
                if not data:
                    raise ValueError("Original member ended before its signed extent")
                prior_pin = "sha256:" + checksum.hexdigest()
                checksum.update(data)
                following = completed + len(data)
                if journal is not None:
                    write_checkpoint(journal, checkpoint(extent, member_identity,
                                     [(completed, prior_pin), (following, "sha256:" + checksum.hexdigest())]))
                if staged.write(data) != len(data):
                    raise OSError("Short write to staged recording")
                completed = following
                pacing.progress(read_s, len(data))
                sleep(max(.025, len(data) / RATE - (perf_counter() - beginning)))
        if identity(os.fstat(entry.fileno())) != member_identity:
            raise ValueError("Original source changed while copying its signed extent")
    if checksum.hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"Original member digest mismatch for {source.name}")
    checked_local(target, size, digest)


def stopped_admission(root):
    data = gzip.decompress(STOPPED_RECEIPT.read_bytes())
    if sha256(data).hexdigest() != STOPPED_SHA:
        raise ValueError("The original stopped-stage receipt differs from its seal")
    saved = json.loads(data)
    if (root / RECORDING.name != Path(saved["partial"]) or saved["inventory_sha256"] != ORIGINAL.inventory
            or saved["completed_signed_stage"] or saved["launches"]):
        raise ValueError("The sealed stopped stage does not match the requested root")
    rows = [(Extent(Path(row["relative"]), row["signed_bytes"], row["signed_sha256"]), row)
            for row in saved["files"]]
    (extent, row), = [(extent, row) for extent,row in rows if 0 < row["staged_bytes"] < extent.size]
    recovered = checkpoint(extent, None, [(row["staged_bytes"], row["staged_sha256"])])
    ordered = [extent for kind in COPY_ORDER for extent,row in rows if row["kind"] == kind]
    return ordered, recovered, {extent.relative for extent,row in rows if row["verified_complete"]}


def existing_stage(root, extents):
    journal = root / "copy-checkpoint.json"
    active = json.loads(journal.read_text()) if journal.exists() else None
    required = set()
    if root == STOPPED_ROOT:
        signed, stopped, required = stopped_admission(root)
        if set(signed) != set(extents):
            raise ValueError("The stopped receipt and original signed extents differ")
        if active is None:
            active = stopped
    complete, partial = verified_extents(root / RECORDING.name, extents, active)
    if active is not None:
        active_relative = Path(active["relative"])
        for extent in extents:
            if extent.relative == active_relative:
                break
            required.add(extent.relative)
    if not required <= complete:
        raise ValueError("A previously verified extent disappeared from the staged recording")
    if root == STOPPED_ROOT and Path(stopped["relative"]) not in complete:
        if partial is None or partial.extent.relative != Path(stopped["relative"]) or partial.offset < stopped["prefixes"][0][0]:
            raise ValueError("The sealed stopped prefix went missing")
    return complete, partial


def inspect_stopped(root):
    with staging_lock(STAGING_LOCK):
        extents, _, _ = stopped_admission(root)
        complete, partial = existing_stage(root, extents)
        total = sum(extent.size for extent in extents)
        count = sum(extent.size for extent in extents if extent.relative in complete)
        return dict(case=ORIGINAL.workload.id, signed_bytes=total, verified_complete_files=len(complete),
                    verified_complete_bytes=count, verified_partial_bytes=partial.offset if partial else 0,
                    verified_partial_path=str(partial.extent.relative) if partial else None,
                    verified_partial_sha256="sha256:" + partial.checksum.hexdigest() if partial else None,
                    remaining_bytes=total - count - (partial.offset if partial else 0),
                    stopped_receipt_sha256=STOPPED_SHA, original_payload_reads=0)


def stage(root, *, resume=False):
    if sorted(os.sched_getaffinity(0)) != [2] or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Expected the low-priority CPU2 pacing worker")
    with staging_lock(STAGING_LOCK):
        stage_locked(root, resume=resume)


def stage_locked(root, *, resume):
    if resume and not root.is_dir():
        raise ValueError("Resume requires an existing stage")
    signed, _, files, extents = signed_members()
    before = cache_states(files)
    total = sum(extents.values())
    enrolled = [Extent(source.relative_to(RECORDING), size, pin)
                for kind in COPY_ORDER for source,size,pin in files[kind]]
    tmpfs = Path("/dev/shm")
    available = os.statvfs(root.parent)
    if root.parent.stat().st_dev != tmpfs.stat().st_dev or root.resolve() != root:
        raise ValueError("Expected a confined stage in local tmpfs")
    if not resume:
        root.mkdir(mode=0o750)
    clocks = (perf_counter(), process_time(), resource.getrusage(resource.RUSAGE_SELF).ru_inblock)
    complete, partial = existing_stage(root, enrolled) if resume else (set(), None)
    reused = sum(extent.size for extent in enrolled if extent.relative in complete) + (partial.offset if partial else 0)
    if (root / "staging.json").is_file():
        previous = json.loads((root / "staging.json").read_text())
        if (previous["inventory"] == ORIGINAL.inventory and
                (previous["copied_bytes"] == total == reused or previous["copied_bytes"] == 0 and fully_resident(before))):
            return
        raise ValueError("The existing staging receipt differs from the current complete input")
    if available.f_bavail * available.f_frsize < total - reused + 512*MB:
        raise ValueError("Expected enough tmpfs capacity for the remaining signed input")
    count, pacing = 0, None
    if reused or resume or not fully_resident(before):
        pacing = Pacing(root, total, reused) if reused < total else None
        staged = root / RECORDING.name
        with LOCK.open("rb") as lock:
            for kind in COPY_ORDER:
                for source, size, digest in files[kind]:
                    relative = source.relative_to(RECORDING)
                    if relative in complete:
                        continue
                    destination = staged / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    prior = partial if partial and relative == partial.extent.relative else None
                    copy_member(source, destination, size, digest, lock, pacing,
                                partial=prior, journal=root / "copy-checkpoint.json")
        count = pacing.copied if pacing else total
        if count != total:
            raise ValueError("The completed copy differed from the authenticated input extent")
        if pacing:
            pacing.record(event="complete")
    blocks = resource.getrusage(resource.RUSAGE_SELF).ru_inblock - clocks[2]
    staged_files = {kind: [(root / RECORDING.name / source.relative_to(RECORDING), size, digest)
                           for source,size,digest in rows] for kind,rows in files.items()} if count else files
    staged_cache = cache_states(staged_files)
    if not fully_resident(staged_cache):
        raise ValueError("The complete benchmark input must be resident")
    receipt = dict(case=ORIGINAL.workload.id, recording=str(RECORDING), raw_authority=signed["case"]["raw_authority"],
                   inventory=ORIGINAL.inventory, files={kind: [[str(p), n, d] for p,n,d in rows] for kind,rows in files.items()},
                   extents=extents, original_before=before, original_after=cache_states(files), benchmark_cache=staged_cache,
                   copied_bytes=count, max_payload_read_bytes=ORIGINAL.workload.compressed_bytes, input_blocks=blocks,
                   reused_verified_bytes=reused, new_copied_bytes=count-reused,
                   stopped_receipt_sha256=STOPPED_SHA if resume and root == STOPPED_ROOT else None,
                   elapsed_s=perf_counter()-clocks[0], cpu_s=process_time()-clocks[1], lock_wait_s=pacing.wait_s if pacing else 0,
                   pauses=pacing.pauses if pacing else 0, rate_limit_bytes_s=RATE)
    with (root / "staging.json").open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true", help="Read only the missing suffixes after a verified checkpoint")
    mode.add_argument("--inspect-stopped", action="store_true", help="Verify the sealed stopped stage without original reads")
    options = cli.parse_args()
    if options.inspect_stopped:
        print(json.dumps(inspect_stopped(options.root), sort_keys=True))
    else:
        stage(options.root, resume=options.resume)
