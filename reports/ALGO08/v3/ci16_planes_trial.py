"""Compare reversible CI16 byte-plane aperture blocks with the resident original."""

import argparse
from collections import Counter
import ctypes as ct
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import resource
import subprocess
from time import perf_counter_ns, process_time_ns

import numpy as np
import zstandard as zstd

from .ci16_packing import Packing, SOURCE as PACK_SOURCE

PREFIX = 80_000 * 8
SOURCE = Path(__file__).with_name("ci16_planes.c")
ARMS = ("ordinary", "packed", "split-zstd", "planes-lz4", "planes-zstd")
ORDERS = (ARMS, ARMS[::-1])
SCHEMA = "private-algo08-ci16-byte-plane-assay-v1"


def clock():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    return dict(cpu_ns=process_time_ns() - start[0], wall_ns=perf_counter_ns() - start[1])


def digest(data):
    return sha256(data).hexdigest()


def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def bytes_view(data):
    return memoryview(data).cast("B").toreadonly()


def pointer(data):
    return np.frombuffer(data, dtype=np.uint8).ctypes.data


def checked_frame(decompressor, encoded, size):
    if zstd.frame_content_size(encoded) != size:
        raise ValueError("Zstandard frame declares a different raw extent")
    return decompressor.decompress(encoded, max_output_size=size, allow_extra_data=False)


class Planes:
    def __init__(self, binary, kind):
        self.native = ct.CDLL(str(binary))
        for function in (self.native.ci16_separate, self.native.ci16_interleave):
            function.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_size_t)
            function.restype = None
        self.kind = kind
        self.compressor = zstd.ZstdCompressor(level=1, write_checksum=True)
        self.decompressor = zstd.ZstdDecompressor()
        if kind == "lz4":
            self.lz4 = ct.CDLL("liblz4.so.1")
            for function in (self.lz4.LZ4_compress_default, self.lz4.LZ4_decompress_safe):
                function.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int)
                function.restype = ct.c_int
            self.lz4.LZ4_compressBound.argtypes = (ct.c_int,)
            self.lz4.LZ4_compressBound.restype = ct.c_int
            self.lz4.LZ4_versionString.restype = ct.c_char_p

    def compress(self, raw):
        if not 0 < len(raw) <= 1_600_000 or len(raw) % 8:
            raise ValueError("Expected an integral bounded little-endian stereo extent")
        half = len(raw) // 2
        high = np.empty(half, dtype=np.uint8)
        if self.kind == "lz4":
            capacity = self.lz4.LZ4_compressBound(half)
            encoded = np.empty(half + capacity, dtype=np.uint8)
            self.native.ci16_separate(pointer(raw), encoded.ctypes.data, high.ctypes.data, half // 4)
            length = self.lz4.LZ4_compress_default(high.ctypes.data, encoded.ctypes.data + half, half, capacity)
            if length <= 0:
                raise ValueError("LZ4 high-plane compression failed")
            return bytes_view(encoded[:half + length])
        low = np.empty(half, dtype=np.uint8)
        self.native.ci16_separate(pointer(raw), low.ctypes.data, high.ctypes.data, half // 4)
        return b"".join((bytes_view(low), self.compressor.compress(high)))

    def decode(self, encoded, size):
        if not 0 < size <= 1_600_000 or size % 8 or len(encoded) <= size // 2:
            raise ValueError("Encoded high planes do not match the requested extent")
        half = size // 2
        encoded = bytes_view(encoded)
        if self.kind == "lz4":
            high = np.empty(half, dtype=np.uint8)
            actual = self.lz4.LZ4_decompress_safe(
                pointer(encoded) + half, high.ctypes.data, len(encoded) - half, half,
            )
            if actual != half:
                raise ValueError("LZ4 returned a different high-plane extent")
        else:
            high = checked_frame(self.decompressor, encoded[half:], half)
            if len(high) != half:
                raise ValueError("Zstandard returned a different high-plane extent")
        raw = np.empty(size, dtype=np.uint8)
        self.native.ci16_interleave(pointer(encoded), pointer(high), raw.ctypes.data, half // 4)
        return bytes_view(raw)


class SplitZstd:
    def __init__(self):
        self.compressor = zstd.ZstdCompressor(level=1, write_checksum=True)
        self.decompressor = zstd.ZstdDecompressor()

    def compress(self, raw):
        return self.compressor.compress(raw)

    def decode(self, encoded, size):
        return checked_frame(self.decompressor, encoded, size)


@dataclass(frozen=True)
class Capture:
    table: bytes
    encoded: tuple

    @property
    def pin(self):
        return digest(self.table)


def split(raw, prefix):
    return (raw[:prefix], raw[prefix:])


def encode(arm, codec, rows, identity, prefix=PREFIX):
    started = clock()
    whole = sha256()
    if codec is None:
        stream = BytesIO()
        compressor = zstd.ZstdCompressor(level=1, write_checksum=True, write_content_size=False)
        with compressor.stream_writer(stream, closefd=False) as writer:
            for raw in rows:
                writer.write(raw)
                whole.update(raw)
        encoded = (stream.getvalue(),)
        records = [[len(raw), digest(raw)] for raw in rows]
        payload = [[len(encoded[0]), digest(encoded[0])]]
    else:
        encoded, records, payload = [], [], []
        for raw in rows:
            prefix_raw, tail_raw = split(raw, prefix)
            prefix_sha = sha256(prefix_raw)
            window_sha = prefix_sha.copy()
            window_sha.update(tail_raw)
            whole.update(raw)
            records.append([len(raw), window_sha.hexdigest()])
            parts = (codec.compress(prefix_raw), codec.compress(tail_raw))
            encoded.extend(parts)
            payload.extend([[len(parts[0]), digest(parts[0]), prefix_sha.hexdigest()],
                            [len(parts[1]), digest(parts[1]), digest(tail_raw)]])
    table = dumps(dict(schema=SCHEMA, arm=arm, original=identity, prefix=prefix, records=records,
                       decoded=whole.hexdigest(), parts=payload))
    capture = Capture(table, tuple(encoded))
    pin = capture.pin
    return capture, pin, elapsed(started)


def decode(arm, codec, capture, pin, rows, identity, requests=None, prefix=PREFIX):
    started = clock()
    if capture.pin != pin:
        raise ValueError("Changed aperture table")
    table = json.loads(capture.table)
    if (table["schema"], table["arm"], table["original"], table["prefix"]) != (SCHEMA, arm, identity, prefix):
        raise ValueError("Aperture table belongs to a different source or codec")
    if len(table["records"]) != len(rows) or len(capture.encoded) != (1 if codec is None else 2 * len(rows)):
        raise ValueError("Aperture table does not cover the original member")
    check_bytes = 0
    for encoded, (size, encoded_sha, *_) in zip(capture.encoded, table["parts"], strict=True):
        if len(encoded) != size or digest(encoded) != encoded_sha:
            raise ValueError("Changed encoded part")
        check_bytes += size
    auth = elapsed(started)
    verified = whole = 0
    actual_sha = sha256()
    direct_comparison = Counter(cpu_ns=0, wall_ns=0)
    if codec is None:
        reader = zstd.ZstdDecompressor().stream_reader(BytesIO(capture.encoded[0]))
    else:
        reader = None
    try:
        for row, (raw, (size, raw_sha)) in enumerate(zip(rows, table["records"], strict=True)):
            if size != len(raw):
                raise ValueError("Original row extent changed")
            if reader is not None:
                expected, decoded = (raw,), (reader.read(size),)
                window = sha256(decoded[0])
            else:
                count = 2 if requests is None else requests[row]
                expected = split(raw, prefix)[:count]
                offsets = range(2 * row, 2 * row + count)
                decoded = tuple(codec.decode(capture.encoded[i], len(part))
                                for i, part in zip(offsets, expected, strict=True))
                if decoded:
                    window = sha256(decoded[0])
                    if window.hexdigest() != table["parts"][2 * row][2]:
                        raise ValueError("Decoded prefix digest differs")
                if len(decoded) == 2:
                    if digest(decoded[1]) != table["parts"][2 * row + 1][2]:
                        raise ValueError("Decoded tail digest differs")
                    window.update(decoded[1])
            for part, own in zip(decoded, expected, strict=True):
                if len(part) != len(own):
                    raise ValueError("Decoded part extent differs")
                test_start = clock()
                identical = np.array_equal(np.frombuffer(part, dtype=np.uint8), np.frombuffer(own, dtype=np.uint8))
                direct_comparison.update(elapsed(test_start))
                if not identical:
                    raise ValueError("Original CI16 bytes differ")
                verified += len(part)
                if reader is not None or requests is None:
                    actual_sha.update(part)
            if reader is not None or len(decoded) == 2:
                if window.hexdigest() != raw_sha:
                    raise ValueError("Original window digest differs")
                whole += 1
        if reader is not None and reader.read(1):
            raise ValueError("Unexpected bytes after the original decoded member")
    finally:
        if reader is not None:
            reader.close()
    if (codec is None or requests is None) and actual_sha.hexdigest() != table["decoded"]:
        raise ValueError("Original member digest differs")
    timing = elapsed(started)
    return dict(clock=timing, authentication=auth, test_only_equality=dict(direct_comparison),
                net_clock={k: n - direct_comparison[k] for k, n in timing.items()},
                decoded_bytes=verified, complete_windows=whole, authenticated_encoded_bytes=check_bytes)


def held_entropy(rows):
    """Held cross-entropy for one independent low and high histogram per component."""
    totals = {}
    for name in ("words", "modulo_difference"):
        histograms = []
        for group in (rows[::8], rows[4::8]):
            counts = np.zeros((4, 2, 256), dtype=np.int64)
            for raw in group:
                words = np.frombuffer(raw, dtype="<u2").reshape(-1, 4)
                if name == "modulo_difference":
                    words = np.diff(words, axis=0, prepend=np.zeros((1, 4), dtype=words.dtype))
                for component, lane in enumerate(words.T):
                    counts[component, 0] += np.bincount(lane & 255, minlength=256)
                    counts[component, 1] += np.bincount(lane >> 8, minlength=256)
            histograms.append(counts)
        train, held = histograms
        probability = (train + 1) / (train.sum(axis=2, keepdims=True) + 256)
        widths = (-held * np.log2(probability)).sum(axis=2) / held.sum(axis=2)
        totals[name] = dict(held_bits_per_byte=widths.tolist(), total_bits_per_component=widths.sum(axis=1).tolist(),
                            ideal_bytes=sum(map(len, rows)) * float(widths.mean()) / 8)
    return totals


def run(output):
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    from . import legacy_block_input as port, legacy_block_seek as core, sparse_cold_input as release
    from .future_capture_storage import qualified
    from .legacy_fresh_0169 import admit
    from .mixed_aperture_receiver import StereoSchedule

    priority = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if (output.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15 or priority != "best-effort: prio 7"
            or not Path(ShortWindowReader.windows.__code__.co_filename).is_relative_to(release.RELEASE)):
        raise ValueError("Use one shared low-priority CPU2 slot and exact installed storage")

    started = clock()
    source, chunk, expected, authority, residency = admit()
    metadata = elapsed(started)
    spec = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    ingress = release.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    hasher = release.PAYLOAD / "paired-sha256.so"
    release.verified(hasher, spec["paired_sha256"]["sha256"])
    started = clock()
    with core.one_member(source.reader.path, chunk), ingress(), paired_decoded_hashes(hasher):
        owned = tuple(port.stock_scope(source.reader, chunk))
    if [window.index.iq_sha256 for window in owned] != expected:
        raise ValueError("Input differs from the signed stock reference")
    rows = tuple(bytes_view(window.samples) for window in owned)
    if len(rows) != 64 or any(window.samples.dtype.str != "<i2" or window.samples.flags.writeable
                              or window.samples.shape != (200_000, 2, 2) for window in owned):
        raise ValueError("Only the enrolled 64 owned and immutable original extents are supported")
    conversion = elapsed(started)
    identity = port.member_identity(source.reader, chunk)
    selector, requests = StereoSchedule(full_coverage=True), []
    targets = {target["target_id"]: target for target in source.reader.manifest.configuration["targets"]}
    for visit in owned:
        row = visit.index
        if qualified(row.acquisition):
            target = targets[row.target_id]
            _, mode = selector.visit(target["edge"], target, row.acquisition)
            requests.append(2 if mode == "full" else 1)
        else:
            requests.append(0)
    if Counter(requests) != {0: 13, 1: 43, 2: 8}:
        raise ValueError("Original eligibility or anchor order changed")

    output.mkdir(mode=0o700)
    builds = {}
    for path in (SOURCE, PACK_SOURCE):
        binary = output / (path.stem + ".so")
        arch = "-mssse3" if path == PACK_SOURCE else "-march=x86-64-v3"
        command = ["cc", "-std=c11", "-O3", "-shared", "-fPIC", arch, "-Wall", "-Wextra", "-Werror",
                   str(path), "-o", str(binary)]
        subprocess.run(command, check=True)
        builds[path.stem] = dict(source=digest(path.read_bytes()), binary=digest(binary.read_bytes()), command=command)
    codecs = dict(zip(ARMS, (None, Packing(output / "ci16_packing.so"), SplitZstd(),
                            Planes(output / "ci16_planes.so", "lz4"), Planes(output / "ci16_planes.so", "zstd")),
                      strict=True))
    results = []
    for order in ORDERS:
        observed = {}
        for arm in order:
            codec = codecs[arm]
            capture, pin, writing = encode(arm, codec, rows, identity)
            table = json.loads(capture.table)
            if table["decoded"] != chunk.uncompressed_sha256.removeprefix("sha256:"):
                raise ValueError("New representation does not bind the original whole decoded SHA")
            if [f"sha256:{item[1]}" for item in table["records"]] != expected:
                raise ValueError("New representation does not bind the original ordered window hashes")
            if codec is None and (len(capture.encoded[0]), table["parts"][0][1]) != (
                    chunk.compressed_bytes, chunk.compressed_sha256.removeprefix("sha256:")):
                raise ValueError("In-memory original writer differs from the released member")
            complete = decode(arm, codec, capture, pin, rows, identity)
            ready = decode(arm, codec, capture, pin, rows, identity, requests=requests)
            observed[arm] = dict(writer=writing, complete=complete, ready=ready,
                                 table_bytes=len(capture.table), table_sha256=pin,
                                 sizes=[sum(map(len, capture.encoded))] if codec is None else
                                 [sum(map(len, capture.encoded[i::2])) for i in (0, 1)])
            del capture
        results.append(observed)
    for arm in ARMS:
        if results[0][arm]["table_sha256"] != results[1][arm]["table_sha256"]:
            raise ValueError("Repeated codec output did not reproduce its own commitment")
    entropy = held_entropy(rows)
    lz4 = next(Path(row.split()[-1]) for row in Path("/proc/self/maps").read_text().splitlines()
               if "/liblz4.so." in row)
    info = dict(affinity=[2], nice=15, ionice=priority, ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    receipt = dict(source_metadata=metadata, legacy_conversion=conversion, originals=identity, authority=authority,
                   residency=residency, builds=builds,
                   lz4=dict(version=codecs["planes-lz4"].lz4.LZ4_versionString().decode(),
                            library=str(lz4), sha256=digest(lz4.read_bytes())),
                   zstd=zstd.ZSTD_VERSION, stage_requests=requests, machine=info, orders=ORDERS, repeats=results,
                   packing=codecs["packed"].counts(), held_entropy=entropy)
    (output / "result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
