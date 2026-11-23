"""Audit exact buffer ownership on one existing signed public tmpfs member."""

import argparse
from collections import Counter
from contextlib import contextmanager
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
import resource
from statistics import median
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.qualification.cache_residency import load_query
from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256, paired_decoded_hashes
from tools.pipeline_eval.variants.experimental.receiver_decoded_ingress import WindowBuffers

from . import full_short_cold as full, sparse_cold_input as cold
from .dense_zstd_backend_trial import BUNDLED_SHA
from .mixed_aperture_receiver import NativePath
from .native_verified_drain import ZSTD, ZSTD_SHA
from .public_short_prefetch import MANIFEST_SHA, RECORDING
from .short_prefetch_residency import resident
from .warm_six_prefetch import ResidentTmpfsReads, archived, page_state, prepare


WINDOWS = 64
MAX_WINDOW = 1_600_000
PAIRED = cold.PAYLOAD / "paired-sha256.so"
ORDERS = (("release", "view"), ("view", "release"))


def signed_member(query):
    data = cold.verified(RECORDING / "manifest.json", MANIFEST_SHA)
    manifest = json.loads(data)
    chunk = manifest["chunks"][0]
    if ((chunk["first_sequence"], chunk["window_count"], chunk["uncompressed_bytes"]) != (0, WINDOWS, WINDOWS*MAX_WINDOW)
            or manifest["receiver_ids"] != [0, 1] or manifest["sample_rate_hz"] != 10_000_000):
        raise ValueError("The original signed public member changed")
    pages, = page_state(RECORDING, (chunk,), query)
    if not all(resident(state) for state in pages.values()):
        raise ValueError("The original public member or index lost residency")
    return chunk, pages


class ObservedStream:
    def __init__(self, stream, use_view, counters, on_read):
        self.original = stream
        self.pooled = WindowBuffers(stream) if use_view and callable(getattr(stream, "readinto", None)) else None
        self.counters = counters
        self.on_read = on_read
        if use_view and self.pooled is None:
            counters["unsupported_streams"] += 1

    def read(self, count):
        reader = self.pooled if self.pooled is not None and 1 < count <= MAX_WINDOW else self.original
        started = process_time_ns()
        raw = reader.read(count)
        self.counters["decoder_cpu_ns"] += process_time_ns()-started
        if count > 1:
            self.counters["window_reads"] += 1
            self.counters["readonly_views" if isinstance(raw, memoryview) else "owned_windows"] += 1
            if self.on_read is not None:
                self.on_read(raw)
        return raw


@contextmanager
def decoded_route(use_view, counters, on_read=None):
    from leo.storage import short_window

    stock = short_window.zstd

    class Decoder:
        @contextmanager
        def stream_reader(self, compressed):
            try:
                counters["history_bytes"] = stock.get_frame_parameters(compressed).window_size
            except stock.ZstdError:
                # Header diagnostics must not replace the released decoder's behavior.
                counters["unavailable_frame_header"] += 1
            with stock.ZstdDecompressor().stream_reader(compressed) as stream:
                yield ObservedStream(stream, use_view, counters, on_read)

    with patch.object(short_window, "zstd", SimpleNamespace(ZstdError=stock.ZstdError, ZstdDecompressor=Decoder)):
        yield


def pinned_zstd():
    import zstandard.backend_c as backend

    path = Path(backend.__file__)
    cold.verified(path, BUNDLED_SHA)
    source = subprocess.check_output(["objdump", "-d", "--disassemble=decompressionreader_read", path], text=True)
    markers = ("xor    %edi,%edi", "PyBytes_FromStringAndSize", "PyBytes_AsStringAndSize", "decompress_input", "safe_pybytes_resize")
    positions = [source.index(word) for word in markers]
    if positions != sorted(positions):
        raise ValueError("Cannot identify the released full-read destination in the C extension")
    return path, sha256(source.encode()).hexdigest()


def measure_copy(windows):
    timings = []
    for repeat in range(8):
        record = {}
        for label in ("view", "copy") if repeat % 2 else ("copy", "view"):
            total, witness, previous = 0, 0, None
            started_wall = perf_counter_ns()
            for w in windows:
                view = memoryview(w.samples).cast("B")
                started = process_time_ns()
                raw = bytes(view) if label == "copy" else view.toreadonly()
                total += process_time_ns()-started
                previous = raw
                witness += raw[0] + raw[-1]
            record[label] = dict(cpu_ns=total, elapsed_including_loop_ns=perf_counter_ns()-started_wall,
                                 witness=witness+previous[0])
        if record["copy"]["witness"] != record["view"]["witness"]:
            raise ValueError("Control ownership paths saw different bytes")
        timings.append(record)
    return timings


def price(output):
    from leo.storage.scanner import ScannerIqStore
    from leo.storage.short_window import ShortWindowReader

    host = full.check_machine()
    zstd_path, machine_code = pinned_zstd()
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    member, before = signed_member(query)
    checked = ResidentTmpfsReads(RECORDING, query)
    counts = Counter()
    with (patch.dict(ScannerIqStore._read_regular.__globals__, {"os": checked}),
          decoded_route(False, counts), paired_decoded_hashes(PAIRED)):
        samples = list(ShortWindowReader(RECORDING).windows(start_sequence=0, stop_sequence=WINDOWS))
    if len(samples) != WINDOWS or counts["owned_windows"] != WINDOWS:
        raise ValueError("The released owned-window route changed")
    for window in samples:
        view = memoryview(window.samples).cast("B")
        if (np.frombuffer(view, dtype=np.uint8).ctypes.data != window.samples.ctypes.data
                or not view.readonly or len(view) != MAX_WINDOW):
            raise ValueError("The NumPy boundary copied or altered the verified samples")
    timings = measure_copy(samples)
    cold.verified(ZSTD, ZSTD_SHA)
    minimum_buffer = ct.CDLL(str(ZSTD)).ZSTD_decodingBufferSize_min
    minimum_buffer.argtypes, minimum_buffer.restype = (ct.c_ulonglong, ct.c_ulonglong), ct.c_size_t
    ring_capacity = minimum_buffer(counts["history_bytes"], member["uncompressed_bytes"])
    _, after = signed_member(query)
    full.freeze(output, dict(member=member, resident_before=before, resident_after=after, host=host,
                decoder=dict(path=str(zstd_path), sha256=BUNDLED_SHA, read_disassembly_sha256=machine_code),
                counts=counts, ring_capacity=ring_capacity, window_bytes=MAX_WINDOW, timings=timings,
                copy_only_cpu_ns=median(row["copy"]["cpu_ns"]-row["view"]["cpu_ns"] for row in timings),
                source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


def worker(mode, request, binary, target):
    from leo.storage.scanner import ScannerIqStore

    full.check_machine()
    pinned_zstd()
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    cold.verified(PAIRED, spec["paired_sha256"]["sha256"])
    if not PairedSha256(PAIRED).hardware:
        raise ValueError("The paired verification hardware is unavailable")
    info = json.loads(request.read_bytes())
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    checked = ResidentTmpfsReads(RECORDING, query)
    counts, last, hashed = Counter(), None, None
    paired, run = PairedSha256.window, NativePath.run

    def read(raw):
        nonlocal last
        view = np.frombuffer(raw, dtype=np.uint8)
        if view.flags.writeable:
            raise ValueError("Verified decoded intake must be readonly")
        last = view.ctypes.data

    def hash_window(engine, raw):
        nonlocal hashed
        hashed = np.frombuffer(raw, dtype=np.uint8).ctypes.data
        if hashed != last:
            raise ValueError("Digest read a different buffer from the decoder")
        counts["hash_alias"] += 1
        return paired(engine, raw)

    def verify_callback(engine, samples, lane, center):
        if samples.ctypes.data != hashed or samples.flags.writeable:
            raise ValueError("Native callback did not consume the verified readonly storage")
        counts["native_alias"] += 1
        return run(engine, samples, lane, center)

    with (patch.object(cold, "WINDOWS", WINDOWS),
          patch.dict(ScannerIqStore._read_regular.__globals__, {"os": checked}),
          patch.object(PairedSha256, "window", hash_window),
          patch.object(NativePath, "run", verify_callback),
          decoded_route(mode == "view", counts, read)):
        row = full.scope("full-short", request.parent / "assets", binary, spec, info, target)
    if counts["hash_alias"] != WINDOWS or counts["native_alias"] != 2*WINDOWS:
        raise ValueError("The original signed cycle did not traverse the expected ports")
    full.freeze(target.with_suffix(".receipt.json"), dict(row, counts=counts, mode=mode,
                                                        source_read_bytes=checked.logical_bytes))


def measure(binary, output):
    full.check_machine()
    pinned_zstd()
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    chunk, _ = signed_member(query)
    output.mkdir()
    original, native_sha = archived("north")
    request, _ = prepare(dict(case="north", segment=str(RECORDING), manifest_sha256="sha256:"+MANIFEST_SHA,
                              chunks=[chunk]), output, binary)
    base = [row for row in original["source"]["probes"] if row["visit_index"] < WINDOWS]
    rows = []
    for pair, modes in enumerate(ORDERS, 1):
        for mode in modes:
            _, before_pages = signed_member(query)
            target = output / f"{pair}-{mode}.json"
            command = [sys.executable, "-BPs", "-m", __spec__.name, "worker", mode, request, binary, target]
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            started = perf_counter_ns()
            subprocess.run(command, timeout=12, check=True)
            wall = perf_counter_ns()-started
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            _, after_pages = signed_member(query)
            row = json.loads(target.with_suffix(".receipt.json").read_bytes())
            doc = json.loads(cold.verified(target, row["sealed_detection_sha256"]))
            if (doc["source"]["probes"] != base or doc["clock_anchor"] != original["clock_anchor"]
                    or doc["delivery_clocks"] != original["delivery_clocks"][:WINDOWS]
                    or len(row["decoded_iq_hashes"]) != WINDOWS or row["counts"]["window_reads"] != WINDOWS
                    or row["counts"].get("readonly_views", 0) != (WINDOWS if mode == "view" else 0)):
                raise ValueError("The scoped ownership path altered original signed output or did not lend all windows")
            row.update(pair=pair, pages_before=before_pages, pages_after=after_pages, process_wall_ns=wall,
                       process_cpu_s=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                       process_input_blocks=after.ru_inblock-before.ru_inblock)
            rows.append(row)
    if len({row["sealed_detection_sha256"] for row in rows}) != 1:
        raise ValueError("Complete signed detector bytes changed")
    full.freeze(output / "comparison.json", dict(arms=rows, member=chunk, original_detector_sha256=native_sha,
                                                 original_factors=sum(len(r["candidates"]) for r in base),
                                                 source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("price").add_argument("output", type=Path)
    pair = commands.add_parser("measure")
    pair.add_argument("binary", type=Path)
    pair.add_argument("output", type=Path)
    child = commands.add_parser("worker")
    child.add_argument("mode", choices=("release", "view"))
    for name in ("request", "binary", "target"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    {"price": price, "measure": measure, "worker": worker}[args.pop("command")](**args)
