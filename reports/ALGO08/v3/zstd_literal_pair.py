"""Decode pairs of independent four-stream Huffman blocks under original checks."""

from dataclasses import dataclass
import ctypes as ct
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

import numpy as np

from .zstd_structure import inspect, literal_section


HERE = Path(__file__).resolve().parent
STATIC = Path("/usr/lib/x86_64-linux-gnu/libzstd.a")
SHARED = Path("/usr/lib/x86_64-linux-gnu/libzstd.so.1")
STATIC_PIN = "eb4f645520aefe163b0a9e209e4efe4c1bc36b303235a7430425d0ad3cccd977"
SHARED_PIN = "060eeb79531d435306665fd78329d8a9dd579f95876c5960bb67937825362a80"
HEADER_PIN = "9b4bc8245565c98ccfc61c07749928b57e7c0f6fddb0530c4f6aa1971893d88b"
MAX_EXTENT = 128 << 20


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


class Literal(ct.Structure):
    _fields_ = [(name, ct.c_uint32) for name in
                ("offset", "encoded", "decoded", "fresh", "block_offset", "mixed_encoded")]


class Work(ct.Structure):
    _fields_ = [(name, ct.c_uint32) for name in
                ("pair_count", "different_tables", "singletons", "tables", "mixed_blocks", "history_bytes")]


class OwnedWork(ct.Structure):
    _fields_ = [(name, ct.c_size_t) for name in
                ("spill_bytes", "seam_copy_bytes", "workspace_bytes", "mixed_zstd_context_bytes")]


def build(output):
    if sys.byteorder != "little" or tuple(sha256(path.read_bytes()).hexdigest() for path in
                                         (STATIC, SHARED, Path("/usr/include/zstd.h"))) != (STATIC_PIN, SHARED_PIN, HEADER_PIN):
        raise ValueError("Pinned native Zstd 1.5.7 inputs or endian ABI changed")
    if output.exists():
        raise ValueError("Use a new output library path")
    subprocess.run(["cc", "-O3", "-std=c11", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                    str(HERE / "zstd_literal_pair.c"), str(STATIC), "-o", str(output)], check=True)
    return digest(output.read_bytes())


def plan(frame, decoded):
    spans = []
    try:
        shape = inspect(frame, decoded, block_spans=spans)
    except ValueError:
        return None
    if (not shape["checksum"] or frame[4] & 3 or not spans
            or shape["block_counts"] != {"compressed": len(spans)}
            or shape["huffman_streams"] != {"4": len(spans)}
            or len(spans) - shape["zero_sequence_blocks"] > 1):
        return None
    rows = []
    view = memoryview(frame)
    for start, size, _, sequences in spans:
        kind, head, encoded, raw, _ = literal_section(view[start:start + size])
        fresh = kind == "huffman_new"
        if sequences:
            if not fresh or (frame[start - 3] & 1 and shape["frame_content_size"] is not None):
                return None
            raw += shape["match_bytes"]
        rows.append((start + head, encoded, raw, int(fresh), start - 3, size if sequences else 0))
    return rows


@dataclass(frozen=True)
class Authority:
    encoded_bytes: int
    encoded_sha256: str
    decoded_bytes: int
    decoded_sha256: str
    windows: tuple


class Decoder:
    def __init__(self, candidate_so, expected):
        if (digest(candidate_so.read_bytes()) != expected or
                digest(SHARED.read_bytes()) != "sha256:" + SHARED_PIN):
            raise ValueError("The original or experimental decoder differs from its pin")
        stock, candidate = ct.CDLL(str(SHARED)), ct.CDLL(str(candidate_so))
        p, u = ct.c_void_p, ct.c_size_t
        self.stock = stock.ZSTD_decompress
        self.stock.argtypes, self.stock.restype = (p, u, p, u), u
        self.size = stock.ZSTD_findFrameCompressedSize
        self.size.argtypes, self.size.restype = (p, u), u
        self.pair = candidate.literal_pair_frame
        self.pair.argtypes = (p, u, ct.POINTER(Literal), u, p, u, ct.POINTER(Work))
        self.pair.restype = ct.c_int
        for name, result, args in (
            ("open", p, (p, u, u, u)), ("read", ct.c_int, (p, p, u)), ("close", None, (p,)),
            ("scratch", u, (p,)), ("finish", ct.c_int, (p, ct.POINTER(Work), ct.POINTER(OwnedWork))),
        ):
            function = getattr(candidate, f"literal_pair_owned_{name}")
            function.argtypes, function.restype = args, result
            setattr(self, f"owned_{name}", function)

    def verified(self, frame, receipt, *, paired=False):
        if (not isinstance(frame, bytes) or not 0 < receipt.decoded_bytes <= MAX_EXTENT
                or not 0 < receipt.encoded_bytes == len(frame) <= MAX_EXTENT
                or digest(frame) != receipt.encoded_sha256):
            raise ValueError("Complete immutable encoded member differs from its authority")
        source = np.frombuffer(frame, dtype=np.uint8)
        output = np.empty(receipt.decoded_bytes, dtype=np.uint8)
        src, raw = source.ctypes.data, output.ctypes.data
        stats = Work()
        original_rows = plan(frame, len(output)) if paired else None
        outcome = "ordinary"
        if original_rows is not None:
            rows = (Literal * len(original_rows))(*(Literal(*row) for row in original_rows))
            if self.pair(src, len(source), rows, len(rows), raw, len(output), ct.byref(stats)) == 0:
                outcome = "paired"
        if outcome != "paired":
            if self.size(src, len(source)) != len(source) or self.stock(raw, len(output), src, len(source)) != len(output):
                raise ValueError("Original complete single frame, checksum or decoded extent failed")
            if paired:
                outcome = "ordinary_fallback"
            stats = Work()
        output.flags.writeable = False
        decoded = memoryview(output)
        if digest(decoded) != receipt.decoded_sha256:
            raise ValueError("Original decoded member digest failed")
        first = 0
        for size, pin in receipt.windows:
            if size <= 0 or first + size > len(decoded) or digest(decoded[first:first + size]) != pin:
                raise ValueError("Original decoded window extent or digest failed")
            first += size
        if first != len(decoded):
            raise ValueError("Original ordered window extent differs from the decoded member")
        return decoded, dict(route=outcome, candidate_eligible=original_rows is not None,
                             decoded_arena_bytes=len(output), original_encoded_bytes=len(frame),
                             **{name: getattr(stats, name) for name, _ in stats._fields_})
