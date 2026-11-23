"""Measure a verified no-array drain for two entirely unpaid signed members."""

import argparse
from contextlib import closing, contextmanager
import ctypes as ct
from dataclasses import dataclass, field
from importlib import import_module
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns, thread_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from . import sparse_cold_input as cold


ZSTD = Path("/usr/lib/x86_64-linux-gnu/libzstd.so.1")
ZSTD_SHA = "060eeb79531d435306665fd78329d8a9dd579f95876c5960bb67937825362a80"
ORDERS = (("released", "native"), ("native", "released"))
UNSUPPORTED = 1
ERRORS = {
    2: "decoded window or member extent changed",
    3: "invalid short-window compressed frame",
    4: "decoded window digest changed",
    5: "decoded member digest changed",
}


class SignedWindow(ct.Structure):
    _fields_ = [("size", ct.c_size_t), ("digest", ct.c_uint8 * 32)]


class NativeStats(ct.Structure):
    _fields_ = [(name, ct.c_uint64) for name in (
        "decode_cpu_ns", "hash_cpu_ns", "decoded_bytes", "frame_header_bytes", "history_bytes",
        "block_bytes", "content_size", "checksum", "windows",
    )]


@dataclass
class TailStats:
    cpu_ns: int = 0
    wall_ns: int = 0
    materialized_rows: int = 0
    retained_metadata_rows: int = 0
    fallbacks: int = 0
    members: list = field(default_factory=list)


def build(work, hasher, zstd=ZSTD):
    from hashlib import sha256

    source = Path(__file__).with_name("native_verified_drain.c")
    binary = work / "native-drain.so"
    cmd = ["cc", "-O3", "-Wall", "-Wextra", "-Werror", "-std=c11", "-shared", "-fPIC", str(source),
           str(zstd), str(hasher), f"-Wl,-rpath,{hasher.parent}", "-Wl,-z,defs", "-o", str(binary)]
    subprocess.run(cmd, check=True)
    return binary, dict(command=cmd, source_sha256=sha256(source.read_bytes()).hexdigest(),
                        binary_sha256=sha256(binary.read_bytes()).hexdigest())


def digest_bytes(value):
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError("Expected a SHA-256 field")
    return (ct.c_uint8 * 32).from_buffer_copy(bytes.fromhex(value[7:]))


class NativeDrain:
    def __init__(self, binary):
        library = ct.CDLL(str(binary))
        create = library.verified_drain_create
        create.argtypes, create.restype = [], ct.c_void_p
        self.free = library.verified_drain_free
        self.free.argtypes, self.free.restype = [ct.c_void_p], None
        self.verify = library.verified_drain_member
        self.verify.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.POINTER(SignedWindow),
                                ct.c_size_t, ct.c_size_t, ct.POINTER(ct.c_uint8), ct.POINTER(NativeStats)]
        self.verify.restype = ct.c_int
        self.context = create()
        if not self.context:
            raise ValueError("Native verification memory or paired SHA-256 ABI check failed")

    def close(self):
        self.free(self.context)

    def check(self, compressed, rows, chunk):
        from leo.storage.errors import BundleCorruptionError
        import numpy as np

        records = (SignedWindow * len(rows))(*(SignedWindow(row.payload_bytes, digest_bytes(row.iq_sha256))
                                              for row in rows))
        pinned = np.frombuffer(compressed, dtype=np.uint8)
        raw = digest_bytes(chunk.uncompressed_sha256)
        stats = NativeStats()
        result = self.verify(self.context, pinned.ctypes.data, pinned.nbytes, records, len(rows),
                             chunk.uncompressed_bytes, raw, ct.byref(stats))
        if result == UNSUPPORTED:
            return None
        if result:
            raise BundleCorruptionError(ERRORS[result])
        report = {key: getattr(stats, key) for key, _ in stats._fields_}
        if report["content_size"] == 2**64 - 1:
            report["content_size"] = None
        return report


def native_tail(source, native, stats):
    from .first_third_ingress import chunk_rows, scope_chunks, window

    for chunk in scope_chunks(source):
        if chunk.first_sequence < cold.WINDOWS_PER_MEMBER:
            continue
        if chunk.first_sequence + chunk.window_count > source.stop_sequence:
            raise ValueError("Native drain requires a whole unpaid member")
        start = thread_time_ns()
        rows = chunk_rows(source, chunk)
        index_cpu = thread_time_ns() - start
        cpu, wall = thread_time_ns(), perf_counter_ns()
        compressed = source.reader._member(chunk.payload_relative_path, chunk.compressed_bytes,
                                           chunk.compressed_sha256)
        read_cpu, read_wall = thread_time_ns() - cpu, perf_counter_ns() - wall
        details = native.check(compressed, rows, chunk)
        del compressed
        if details is None:
            stats.fallbacks += 1
            with closing(source.reader.windows(start_sequence=chunk.first_sequence,
                                               stop_sequence=chunk.first_sequence + chunk.window_count)) as reader:
                for result in reader:
                    stats.materialized_rows += 1
                    yield window(source, result.index, result.samples)
            continue
        stats.members.append(dict(**details, first_sequence=chunk.first_sequence,
                                  index_cpu_ns=index_cpu, compressed_cpu_ns=read_cpu,
                                  compressed_wall_ns=read_wall, compressed_bytes=chunk.compressed_bytes))
        for row in rows:
            stats.retained_metadata_rows += 1
            yield window(source, row, SimpleNamespace(shape=(row.sample_count, row.receiver_count, 2)))


@contextmanager
def timed_tail(native):
    from leo.storage.fast_scan import FastSegmentSource

    released = FastSegmentSource.windows
    stats = TailStats()

    def windows(source):
        if (source.start_sequence, source.stop_sequence) != (0, cold.WINDOWS):
            raise ValueError("Unexpected verify-only measurement scope")

        def mixed():
            entry = dict(path=str(source.reader.path), manifest_digest=source.manifest_digest)
            first = FastSegmentSource(entry, stop_sequence=cold.WINDOWS_PER_MEMBER)
            with closing(released(first)) as stock:
                yield from stock
            yield from native_tail(source, native, stats)

        first_clock = None
        with closing(mixed() if native is not None else released(source)) as items:
            for item in items:
                if native is None and item.sequence >= cold.WINDOWS_PER_MEMBER:
                    stats.materialized_rows += 1
                yield item
                if item.sequence == cold.WINDOWS_PER_MEMBER - 1:
                    first_clock = thread_time_ns(), perf_counter_ns()
        if first_clock is None:
            raise ValueError("Missing whole-member boundary")
        stats.cpu_ns = thread_time_ns() - first_clock[0]
        stats.wall_ns = perf_counter_ns() - first_clock[1]

    with patch.object(FastSegmentSource, "windows", windows):
        yield stats


def run(parent, work):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256
    from .scout_readout_trial import PILOT_SHA, check_machine

    machine = check_machine()
    parent = parent.resolve(strict=True)
    if Path("/srv/bulk/leo-dev") not in (parent, *parent.parents):
        raise ValueError("Use the local research XFS staging area")
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip() != "xfs":
        raise ValueError("Expected local XFS")
    spec = json.loads(cold.verified(cold.PAYLOAD/"spec.json", cold.SPEC_SHA))
    for name, pin in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), pin)
    receiver, hasher = cold.PAYLOAD/"receiver.so", cold.PAYLOAD/"paired-sha256.so"
    cold.verified(receiver, spec["detector_sha256"])
    cold.verified(hasher, spec["paired_sha256"]["sha256"])
    cold.verified(ZSTD, ZSTD_SHA)
    if not PairedSha256(hasher).hardware:
        raise ValueError("Expected hardware paired SHA-256")
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    buffer = cold.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    native_path, = (cold.ARCHIVE/"fast-scan-automatic-work").glob("*/detections.json")
    archive = json.loads(cold.verified(native_path, cold.ARCHIVED_DETECTION_SHA))
    session = archive["source"]["session_id"]
    inventory = json.loads((cold.ARCHIVE/"fast-scan-inputs"/f"{session}.json").read_bytes())
    binding = canonical_digest(inventory)
    if archive["source"]["input_manifest_sha256"] != binding:
        raise ValueError("Original full source was not authenticated")
    work.mkdir(exist_ok=False)
    binary, build_receipt = build(work, hasher)
    with TemporaryDirectory(dir=parent, prefix="leo-private-native-drain-") as tmp:
        private = Path(tmp)
        entry, chunks, payloads = cold.copy_prefix(private, inventory["segments"][0])
        identities = tuple(cold.private_identity(path, private) for path in payloads)
        page_size = os.sysconf("SC_PAGE_SIZE")
        expected_bytes = sum(pages(chunk.compressed_bytes, page_size)*page_size for chunk in chunks)
        sample = sum(c.compressed_bytes for c in chunks)
        assets = private/"assets"
        assets.mkdir()
        (assets/"cancellation-factors.so").symlink_to(receiver)
        pilot = cold.RELEASE/"assets/lower.f32"
        cold.verified(pilot, PILOT_SHA["lower"])
        (assets/"lower.f32").symlink_to(pilot)
        runs = []
        for order in ORDERS:
            pair = []
            for arm in order:
                start_pages = [cold.cache_pages(path, private, identity, query, cold=True)
                               for path, identity in zip(payloads, identities, strict=True)]
                if any(start_pages):
                    raise ValueError("Unexpected private page cache residency")
                # Instantiate the native decoder and scratch allocation within
                # the acquisition boundary so each arm pays its setup.
                @contextmanager
                def context():
                    if arm == "released":
                        with timed_tail(None) as stats:
                            yield stats
                    else:
                        with closing(NativeDrain(binary)) as native, timed_tail(native) as stats:
                            yield stats

                row = cold.measure("advice", assets, hasher, spec, entry, archive, binding, sample,
                                   buffer=buffer, advice=context)
                row.update(arm=arm, initial_file_pages=start_pages)
                tail = row["overlap"]
                expected = (128, 0, 0) if arm == "released" else (0, 128, 2)
                actual = (tail["materialized_rows"], tail["retained_metadata_rows"], len(tail["members"]))
                if (actual != expected or tail["fallbacks"] or row["process_io_delta"]["read_bytes"] < expected_bytes
                        or not tail["wall_ns"] or not tail["cpu_ns"]):
                    raise ValueError("The timing did not include the expected cold verified scope")
                pair.append(row)
            runs.append(pair)
        result = [row for pair in runs for row in pair]
        if len({r["acquisition_sha256"] for r in result}) != 1:
            raise ValueError("Native drain changed the complete acquisition output")
        return dict(runs=runs, orders=ORDERS, machine=machine, build=build_receipt,
                    zstd_sha256=ZSTD_SHA, specification_sha256=cold.SPEC_SHA,
                    manifest_sha256=cold.MANIFEST_SHA, archive_sha256=cold.ARCHIVED_DETECTION_SHA,
                    cache_helper_sha256=cold.CACHE_SHA, native_receiver=spec["detector_sha256"],
                    paired_hash=spec["paired_sha256"]["sha256"], compressed_bytes=sample,
                    decoded_bytes=sum(chunk.uncompressed_bytes for chunk in chunks),
                    expected_payload_page_bytes=expected_bytes,
                    members=[chunk.model_dump(mode="json") for chunk in chunks])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=lambda path: Path(path).resolve())
    parser.add_argument("--parent", type=Path, default=Path("/srv/bulk/leo-dev"))
    args = parser.parse_args()
    print(json.dumps(run(args.parent, args.work), indent=2, allow_nan=False))
