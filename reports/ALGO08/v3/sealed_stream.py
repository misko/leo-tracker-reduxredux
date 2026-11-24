"""Seal a bounded ordinary Zstandard member directly into immutable decoded storage."""

import argparse
from contextlib import contextmanager
import ctypes as ct
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from types import FunctionType, SimpleNamespace
from unittest.mock import patch

from .dense_zstd_backend import _bytes_data, _bytes_new
from .eight_ms_primary import write
from .fused_block_input import VerifiedDecode
from .native_verified_drain import ZSTD, ZSTD_SHA
from .sparse_cold_input import PAYLOAD, SPEC_SHA, verified


SOURCE = Path(__file__).with_suffix(".c")
CAP = 128 * 1024**2
FAILED = {2: "compressed descriptor", 3: "Zstandard frame", 4: "decoded extent",
          5: "compressed SHA-256", 6: "window SHA-256", 7: "decoded member SHA-256", 8: "native setup"}
COUNTERS = ("read_cpu_ns", "compressed_hash_cpu_ns", "decode_cpu_ns", "window_hash_cpu_ns",
            "reads", "compressed_bytes", "decoded_bytes", "windows", "history_bytes")


class Window(ct.Structure):
    _fields_ = [("size", ct.c_size_t), ("expected", ct.c_uint8*32), ("actual", ct.c_uint8*32)]


def binary_digest(path):
    return sha256(path.read_bytes()).hexdigest()


def build(root):
    specification = json.loads(verified(PAYLOAD / "spec.json", SPEC_SHA))
    paired = PAYLOAD / "paired-sha256.so"
    hash_pin = specification["paired_sha256"]["sha256"]
    verified(paired, hash_pin)
    verified(ZSTD, ZSTD_SHA)
    root.mkdir()
    library = root / "sealed-stream.so"
    command = ["cc", "-O3", "-std=c11", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
               "-Wno-deprecated-declarations", str(SOURCE), str(ZSTD), str(paired), "-lcrypto",
               "-Wl,-z,defs", f"-Wl,-rpath,{paired.parent}", "-o", str(library)]
    subprocess.run(command, check=True)
    write(root / "build.json", dict(command=command, source_sha256=binary_digest(SOURCE),
                                   paired_sha256=hash_pin, zstd_sha256=ZSTD_SHA, sha256=binary_digest(library)))


class Native:
    def __init__(self, library):
        self.library = ct.CDLL(str(library))
        self.decode = self.library.sealed_stream_decode
        self.decode.restype = ct.c_int
        self.decode.argtypes = [ct.c_int, ct.c_size_t, ct.c_char_p, ct.c_void_p, ct.c_size_t,
                                ct.POINTER(Window), ct.c_size_t, ct.c_char_p, ct.c_void_p, ct.POINTER(ct.c_uint64)]

    def prepare(self, path, chunk, rows):
        points = chunk["uncompressed_bytes"]
        length = chunk["compressed_bytes"]
        if not 0 < points <= CAP or not 0 < length <= CAP or len(rows) != chunk["window_count"]:
            return 1, None
        output = _bytes_new(None, points)
        digests = (Window*len(rows))()
        for row, (size, pin) in zip(digests, rows, strict=True):
            if not 0 < size <= 1_600_000 or len(pin) != 32:
                return 1, None
            row.size, row.expected[:] = size, pin
        compressed = bytes.fromhex(chunk["compressed_sha256"].removeprefix("sha256:"))
        expected = bytes.fromhex(chunk["uncompressed_sha256"].removeprefix("sha256:"))
        if len(compressed) != 32 or len(expected) != 32:
            raise ValueError("Invalid signed SHA-256 digest extent")
        member = ct.create_string_buffer(32)
        counters = (ct.c_uint64*len(COUNTERS))()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            status = self.decode(fd, length, compressed, _bytes_data(output), points, digests, len(rows),
                                 expected, member, counters)
        finally:
            os.close(fd)
        if status:
            return status, None
        return 0, Slab(output, tuple((row.size, bytes(row.actual)) for row in digests),
                       member.raw.hex(), dict(zip(COUNTERS, counters, strict=True)))


class Slab:
    def __init__(self, data, windows, digest, counters):
        self.data = memoryview(data)
        self.windows, self.digest, self.counters = windows, digest, counters


class Stream(VerifiedDecode):
    @contextmanager
    def stream_reader(self, compressed):
        self.fused = isinstance(compressed, Slab)
        if not self.fused:
            self.stock.new_chunk()
            with self.zstd.ZstdDecompressor().stream_reader(compressed) as reader:
                yield reader
            return
        position = index = 0

        def read(size):
            nonlocal position, index
            if self.pending is not None:
                raise RuntimeError("The original reader left a decoded window unchecked")
            if index == len(compressed.windows) and size == 1:
                self.final = compressed.digest
                return b""
            if index >= len(compressed.windows) or size != compressed.windows[index][0]:
                raise self.zstd.ZstdError("The released reader asked for a different decoded extent")
            raw = compressed.data[position:position+size]
            self.pending = raw, compressed.windows[index][1]
            position += size
            index += 1
            return raw

        yield SimpleNamespace(read=read)
        if self.final is None:
            raise self.zstd.ZstdError("The released reader did not drain the bound member")


@contextmanager
def sealed_windows(native, paired, root, chunk, stats):
    from leo.storage import short_window
    from leo.storage.errors import BundleCorruptionError
    from leo.storage.uri import confined_path

    original = short_window.ShortWindowReader.windows
    read_member = short_window.ShortWindowReader._member
    decoder = original.__globals__["zstd"]
    index_name, payload = chunk["index_relative_path"], chunk["payload_relative_path"]
    bindings = {index_name: (chunk["index_bytes"], chunk["index_sha256"]),
                payload: (chunk["compressed_bytes"], chunk["compressed_sha256"])}
    opened = set()
    pending = None

    def _member(reader, name, size, digest):
        nonlocal pending
        if reader.path != root or bindings.get(name) != (size, digest) or name in opened:
            raise ValueError("The activated decoder received a different signed member")
        opened.add(name)
        if name == index_name:
            pending = read_member(reader, name, size, digest)
            return pending
        if pending is None:
            raise ValueError("The original index must authenticate before member decoding")
        rows = [json.loads(line) for line in pending.splitlines()]
        expected = [(row["payload_bytes"], bytes.fromhex(row["iq_sha256"].removeprefix("sha256:"))) for row in rows]
        path = confined_path(root, root / name, must_exist=True)
        status, slab = native.prepare(path, chunk, expected)
        if status in (1, 3, 4, 8):
            stats["fallback"] = status
            return read_member(reader, name, size, digest)
        if status:
            raise BundleCorruptionError(f"Signed Zstandard member failed {FAILED[status]} validation")
        stats.update(slab.counters)
        stats["decoded_sha256"] = "sha256:" + slab.digest
        return slab

    def windows(reader, **scope):
        engine = Stream(native, paired, decoder, stats)
        globals_ = original.__globals__ | dict(zstd=SimpleNamespace(ZstdError=decoder.ZstdError,
                                                                    ZstdDecompressor=lambda: engine),
                                               hashlib=SimpleNamespace(sha256=engine.new_chunk),
                                               sha256_digest=engine.window_digest)
        method = FunctionType(original.__code__, globals_, argdefs=original.__defaults__)
        method.__kwdefaults__ = original.__kwdefaults__
        yield from method(reader, **scope)

    with (patch.object(short_window.ShortWindowReader, "windows", windows),
          patch.object(short_window.ShortWindowReader, "_member", _member)):
        yield
        if opened != set(bindings):
            raise ValueError("The acquisition did not fully authenticate the two signed member inputs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
