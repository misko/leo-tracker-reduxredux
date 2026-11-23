"""Bound verified mixed-aperture acquisition to already-resident signed pages."""

import argparse
from contextlib import ExitStack, contextmanager, nullcontext
import ctypes as ct
from dataclasses import asdict
import errno
from hashlib import sha256
from importlib import import_module
import json
from math import ceil
import os
from pathlib import Path
import resource
import subprocess
import sys
from threading import Lock
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from . import full_short_cold as full, physical_stage_envelope as ladder, sparse_cold_input as cold
from .short_prefetch_residency import PINNED, resident
from .signed_ingress_reuse import AcquisitionCosts


MEMBERS, WINDOWS = 6, 384
ORDERS = ("serial", "prefetch", "prefetch", "serial", "verify-only")
PACKETS = {
    "DS30-0008": ("/dev/shm/leo-aperture-factor-position-02/prefix", ladder.ARCHIVED_DSP_SHA),
    "DS30-0016": ("/dev/shm/leo-eight-ms-DS30-0016-warm/12ms", "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"),
    "north": ("/dev/shm/leo-eight-ms-north/12ms", "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427"),
}
NORTH_MANIFEST = "0205ca2d10c1282f6c782c93a32d2bff1ae8a7b39ff959c93b4ca3613f0f07eb"


class ColdPage(RuntimeError):
    pass


class Iovec(ct.Structure):
    _fields_ = [("base", ct.c_void_p), ("length", ct.c_size_t)]


def read_nowait(fd, buffers, offset):
    # The release Python was built without preadv2 flags, although Linux supplies the syscall.
    anchors = [ct.c_char.from_buffer(buffer) for buffer in buffers]
    vectors = (Iovec * len(buffers))(*(Iovec(ct.addressof(a), len(b)) for a, b in zip(anchors, buffers, strict=True)))
    operation = ct.CDLL(None, use_errno=True).preadv2
    operation.argtypes = (ct.c_int, ct.POINTER(Iovec), ct.c_int, ct.c_longlong, ct.c_int)
    operation.restype = ct.c_ssize_t
    count = operation(fd, vectors, len(vectors), offset, getattr(os, "RWF_NOWAIT", 8))
    if count == -1:
        error = ct.get_errno()
        raise OSError(error, os.strerror(error))
    return count


class ResidentReads:
    """Keep descriptor semantics while refusing any demand read that would block."""

    def __getattr__(self, name):
        return getattr(os, name)

    def readv(self, fd, buffers):
        start = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            count = read_nowait(fd, buffers, start)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EOPNOTSUPP, errno.ENOSYS, errno.EINVAL):
                raise ColdPage(f"Cache-only descriptor read stopped at offset {start}, errno {exc.errno}") from exc
            raise
        if count:
            os.lseek(fd, count, os.SEEK_CUR)
        return count

    def read(self, fd, size):
        buffer = bytearray(size)
        count = self.readv(fd, [buffer])
        return bytes(memoryview(buffer)[:count])


class ResidentTmpfsReads:
    """Read the public in-memory source after checking each held descriptor."""

    def __init__(self, directory, query):
        filesystem = subprocess.check_output(["findmnt", "-T", directory, "-no", "FSTYPE"], text=True).strip()
        if filesystem != "tmpfs":
            raise ValueError("Descriptor fallback requires the staged public tmpfs")
        self.device = directory.stat().st_dev
        self.query = query
        self.page_size = os.sysconf("SC_PAGE_SIZE")
        self.lock = Lock()
        self.calls = self.logical_bytes = 0

    def __getattr__(self, name):
        return getattr(os, name)

    def check(self, fd):
        info = os.fstat(fd)
        if info.st_dev != self.device or self.query(fd, info.st_size) != ceil(info.st_size / self.page_size):
            raise ColdPage("A held public tmpfs descriptor lost residency")

    def readv(self, fd, buffers):
        self.check(fd)
        count = os.readv(fd, buffers)
        with self.lock:
            self.calls += 1
            self.logical_bytes += count
        return count

    def read(self, fd, size):
        self.check(fd)
        body = os.read(fd, size)
        with self.lock:
            self.calls += 1
            self.logical_bytes += len(body)
        return body


def page_state(segment, chunks, query):
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot

    page_size = os.sysconf("SC_PAGE_SIZE")
    return [{mode: cache_snapshot([(segment, chunk[key], chunk[size])], page_size, query)
             for mode, key, size in (("payload", "payload_relative_path", "compressed_bytes"),
                                     ("index", "index_relative_path", "index_bytes"))}
            for chunk in chunks]


def all_resident(rows):
    return len(rows) == MEMBERS and all(resident(state) for row in rows for state in row.values())


def archived(case):
    directory, digest = PACKETS[case]
    packet, = (Path(directory) / "fast-scan-automatic-work").glob("*/detections.json")
    native = json.loads(cold.verified(packet, digest))
    return native, digest


def inspect(case, query):
    if case == "north":
        from .public_short_prefetch import RECORDING

        path, pin = RECORDING / "manifest.json", NORTH_MANIFEST
    else:
        assignment = json.loads(cold.verified(cold.BINDING.with_name(case+".json"), PINNED[case]))
        first = assignment["case"]["recording"]["segments"][0]
        path, pin = Path("/srv/bulk") / first["path"], first["sha256"]
    doc = json.loads(cold.verified(path, pin))
    chunks = doc["chunks"][:MEMBERS]
    if (doc["sample_rate_hz"] != 10_000_000 or doc["receiver_ids"] != [0, 1]
            or len(chunks) != MEMBERS or any((c["first_sequence"], c["window_count"], c["uncompressed_bytes"])
                                             != (i*64, 64, 102400000) for i, c in enumerate(chunks))
            or sum(c["compressed_bytes"] for c in chunks) > 500 * 1024**2):
        raise ValueError("Unexpected signed six-member geometry")
    return dict(case=case, segment=str(path.parent), manifest_sha256="sha256:"+pin,
                chunks=chunks, pages=page_state(path.parent, chunks, query))


def prepare(selected, output, binary):
    from leo.contracts.digests import canonical_digest

    case = selected["case"]
    native, digest = archived(case)
    session = native["source"]["session_id"]
    inventory_path = Path(PACKETS[case][0]) / "fast-scan-inputs" / (session+".json")
    inventory = json.loads(cold.verified(inventory_path, native["source"]["input_manifest_sha256"]))
    entry = inventory["segments"][0]
    if (entry["path"] != selected["segment"] or entry["manifest_digest"] != selected["manifest_sha256"]
            or canonical_digest(inventory) != native["source"]["input_manifest_sha256"]):
        raise ValueError("Prefix does not bind the authentic acquisition")
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    cold.verified(binary, full.SHORT_SHA)
    cold.verified(cold.PAYLOAD / "receiver.so", spec["detector_sha256"])
    cold.verified(cold.PAYLOAD / "paired-sha256.so", spec["paired_sha256"]["sha256"])
    pilot = cold.RELEASE / "assets/lower.f32"
    cold.verified(pilot, full.PILOT_SHA["lower"])
    assets = output / "assets"
    assets.mkdir()
    (assets / "cancellation-factors.so").symlink_to(cold.PAYLOAD / "receiver.so")
    (assets / pilot.name).symlink_to(pilot)
    request_path = output / "request.json"
    full.freeze(request_path, dict(case=case, session=session, inventory_digest=canonical_digest(inventory), entry=entry,
                                  chunks=selected["chunks"], original_detector_sha256=digest))
    return request_path, native


def worker(mode, request_path, binary, output):
    from leo.storage.fast_scan import immutable_json
    from leo.storage.scanner import ScannerIqStore
    from tools.pipeline_eval.qualification import blind_compact_run
    from tools.pipeline_eval.variants.experimental import receiver_member_prefetch as prefetch
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256

    host = full.check_machine()
    request = json.loads(request_path.read_bytes())
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, digest in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), digest)
    # Validate and map code assets for the fresh process outside the signed payload clock.
    cold.verified(Path(blind_compact_run.__file__), cold.RUNTIME[blind_compact_run.__name__])
    release_binary = cold.PAYLOAD / "receiver.so"
    cold.verified(release_binary, spec["detector_sha256"])
    cold.verified(binary, full.SHORT_SHA)
    cold.verified(cold.RELEASE / "assets/lower.f32", full.PILOT_SHA["lower"])
    assets = [ct.CDLL(path) for path in (release_binary, binary)]
    if not PairedSha256(cold.PAYLOAD / "paired-sha256.so").hardware:
        raise ValueError("Expected released hardware paired SHA-256")
    old_buffer = cold.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    helper, cpus = prefetch.prefetch_member, set()
    collected = []

    def observe(*args):
        affinity = os.sched_getaffinity(0)
        if affinity != {2}:
            raise ValueError("Prefetch must execute on the same CPU")
        cpus.update(affinity)
        return helper(*args)

    @contextmanager
    def buffer():
        context = prefetch.compressed_member_prefetch() if mode == "prefetch" else nullcontext(prefetch.MemberPrefetchStats())
        with old_buffer(), context as overlap:
            yield
        collected.append(asdict(overlap))

    buffer.__wrapped__ = old_buffer.__wrapped__
    costs, reads = AcquisitionCosts(), ResidentReads()
    if request["case"] == "north":
        from tools.pipeline_eval.qualification.cache_residency import load_query

        cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
        reads = ResidentTmpfsReads(Path(request["entry"]["path"]), load_query(cold.CACHE_LIBRARY))
    read_modules = [ScannerIqStore._read_regular.__globals__, old_buffer.__wrapped__.__globals__,
                    prefetch.read_regular_descriptor.__globals__]
    with ExitStack() as stack:
        for mapping in read_modules:
            stack.enter_context(patch.dict(mapping, {"os": reads}))
        stack.enter_context(patch.object(ladder, "WINDOWS", WINDOWS))
        stack.enter_context(patch.object(prefetch, "prefetch_member", observe))
        before = ladder.kernel_counters()
        started = process_time_ns(), perf_counter_ns()
        result = ladder.acquired("verify" if mode == "verify-only" else "dsp", request,
                                 request_path.parent / "assets", binary, spec, buffer, costs)
        cpu, wall = process_time_ns()-started[0], perf_counter_ns()-started[1]
        after = ladder.kernel_counters()
    kernel = {key: after[key]-value for key, value in before.items()}
    public = isinstance(reads, ResidentTmpfsReads)
    if not public and (kernel["read_bytes"] or kernel["input_blocks"]):
        full.freeze(output.with_suffix(".aborted.json"), dict(kernel=kernel, duration_ns=wall,
                    resource_iq_scope="checked pre-existing acquisition files", checked=costs.receipt()))
        raise ColdPage(f"Acquisition charged physical storage I/O: {kernel['read_bytes']} bytes")
    del assets

    doc = result.pop("doc")
    seal_start = perf_counter_ns()
    immutable_json(output, doc)
    seal = perf_counter_ns()-seal_start
    result.update(mode=mode, acquire_cpu_ns=cpu, acquire_wall_ns=wall, seal_wall_ns=seal,
                  sha256=sha256(output.read_bytes()).hexdigest(), overlap=collected[0], worker_cpus=sorted(cpus),
                  checked=costs.receipt(), kernel=kernel, host=host, read_policy=type(reads).__name__,
                  public_resident_descriptor_counts=dict(calls=reads.calls, logical_bytes=reads.logical_bytes) if public else None,
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    full.freeze(output.with_suffix(".receipt.json"), result)


def verify(result, doc, original, request):
    from collections import Counter
    from leo.contracts.digests import canonical_digest

    chunks = request["chunks"]
    observed = doc["source"]["probes"]
    rows = [p for p in original["source"]["probes"] if p["visit_index"] < WINDOWS]
    excluded = [row for row in original["provenance"]["excluded_windows"] if row["visit"] < WINDOWS]
    expected = [dict(p, candidates=[]) for p in rows] if result["mode"] == "verify-only" else rows
    pins = [[c[key], c[size], c[digest]] for c in chunks for key, size, digest in (
        ("index_relative_path", "index_bytes", "index_sha256"),
        ("payload_relative_path", "compressed_bytes", "compressed_sha256"))]
    digests = result["decoded_iq_hashes"]
    provenance = doc["provenance"]
    scope = result["checked"]
    raw = canonical_digest([request["inventory_digest"], digests])
    analysis = canonical_digest(["cancellation", raw, provenance["detector_sha256"][7:], observed])
    if (observed != expected or len(digests) != WINDOWS or scope["verified_members"] != pins
            or scope["decoded_members"] != [c["uncompressed_sha256"] for c in chunks]
            or scope["calls"]["decoded_sha"] != WINDOWS+MEMBERS or scope["calls"]["zstd_read"] != WINDOWS+MEMBERS
            or any(digests[e["visit"]] != e["iq_sha256"] for e in excluded)
            or doc["clock_anchor"] != original["clock_anchor"] or doc["delivery_clocks"] != original["delivery_clocks"][:WINDOWS]
            or doc["source"]["raw_recording_authority_digest"] != raw or doc["source"]["analysis_manifest_sha256"] != analysis
            or doc["source"]["input_manifest_sha256"] != request["inventory_digest"]
            or provenance["excluded_windows"] != excluded or provenance["window_count"] != WINDOWS
            or provenance["processed_windows"] != WINDOWS-len(excluded) or provenance["invalid_capture"] != len(excluded)):
        raise ValueError("The signed input, factors, validation or prefix exclusions changed")
    if result["mode"] != "verify-only":
        streams = Counter((p["edge"], p["channel"], p["actual_rf_hz"]) for p in rows if p["receiver_id"] == 0)
        full_lanes = 2 * sum(ceil(n/8) for n in streams.values())
        if result["native"]["native_calls"] != {"full": full_lanes, "short_primary": len(rows)-full_lanes}:
            raise ValueError("The original mixed receiver cadence changed")
    prefetch = result["mode"] == "prefetch"
    overlap = result["overlap"]
    expected_bytes = sum(c["compressed_bytes"] for c in chunks[1:]) if prefetch else 0
    if (overlap["submitted"] != (MEMBERS-1 if prefetch else 0) or overlap["hits"] != overlap["submitted"]
            or overlap["fallback"] or overlap["hit_bytes"] != expected_bytes
            or result["worker_cpus"] != ([2] if prefetch else [])):
        raise ValueError("Bounded helper demand and byte accounting differs")
    return dict(raw_authority=raw, probe_sha256=canonical_digest(observed), factors=sum(len(p["candidates"]) for p in observed),
                admitted=provenance["processed_windows"], excluded=excluded)


def run(binary, output, public_after=None):
    from tools.pipeline_eval.qualification.cache_residency import load_query

    host = full.check_machine()
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    probes, inherited = [], []
    output.mkdir()
    choices = tuple(PACKETS)
    if public_after is not None:
        denied = json.loads(public_after.read_bytes())
        inherited = denied["admission"][:2]
        if (denied["reason"] != "no resident prefix" or [row["case"] for row in inherited] != list(choices[:2])
                or any(all_resident(row["pages"]) for row in inherited)):
            raise ValueError("The public-account fallback needs the same failed physical admission")
        choices = ("north",)
    for case in choices:
        observed = inspect(case, query)
        probes.append(observed)
        if all_resident(observed["pages"]):
            selected = observed
            break
    else:
        full.freeze(output / "stopped.json", dict(reason="no resident prefix", admission=probes))
        return
    full.freeze(output / "admission.json", dict(cases=inherited+probes, selected=selected["case"], host=host))
    request_path, original = prepare(selected, output, binary)
    request = json.loads(request_path.read_bytes())
    chunks, segment = selected["chunks"], Path(selected["segment"])
    compressed = sum(c["compressed_bytes"] for c in chunks)
    rows = []
    for number, mode in enumerate(ORDERS, start=1):
        before_pages = page_state(segment, chunks, query)
        if not all_resident(before_pages):
            full.freeze(output / "stopped.json", dict(reason="resident pages lost", arm=number, pages=before_pages))
            return
        path = output / f"{number}-{mode}.json"
        command = [sys.executable, "-BPs", "-m", __spec__.name, "worker", mode, request_path, binary, path]
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        start = perf_counter_ns()
        process = subprocess.run(command, check=False, timeout=10)
        wall = perf_counter_ns()-start
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        processes = dict(status=process.returncode, wall_ns=wall, cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                         input_blocks=after.ru_inblock-before.ru_inblock)
        full.freeze(path.with_suffix(".process.json"), processes)
        process.check_returncode()
        after_pages = page_state(segment, chunks, query)
        result = json.loads(path.with_suffix(".receipt.json").read_bytes())
        doc = json.loads(cold.verified(path, result["sha256"]))
        if not all_resident(after_pages):
            full.freeze(output / "stopped.json", dict(reason="resident pages lost", arm=number, pages=after_pages))
            return
        result.update(process=processes, scientific=verify(result, doc, original, request), before_pages=before_pages,
                      after_pages=after_pages, compressed_mb_s=1000*compressed/result["acquire_wall_ns"])
        rows.append(result)
    if len({row["sha256"] for row in rows if row["mode"] != "verify-only"}) != 1:
        raise ValueError("Complete measured detector packets differ")
    full.freeze(output / "comparison.json", dict(case=selected["case"], admission=inherited+probes, request=request, arms=rows,
                compressed_bytes=compressed, decoded_bytes=sum(c["uncompressed_bytes"] for c in chunks),
                source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pair = commands.add_parser("run")
    pair.add_argument("binary", type=Path)
    pair.add_argument("output", type=Path)
    pair.add_argument("--public-after", type=Path)
    child = commands.add_parser("worker")
    child.add_argument("mode", choices=sorted(set(ORDERS)))
    for name in ("request_path", "binary", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    mode = args.pop("command")
    {"run": run, "worker": worker}[mode](**args)
