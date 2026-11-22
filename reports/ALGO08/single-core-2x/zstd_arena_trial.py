"""Time Zstandard only on at most two existing complete consecutive chunks."""

import argparse
import gc
import json
from collections import deque
from functools import partial
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time

import numpy as np
import zstandard as zstd

from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.contracts.multirate_window_recording import ShortWindowIndexV2
from leo.contracts.short_window_recording import ShortWindowIndexV1
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.short_window import ShortWindowReader
from leo.storage.uri import confined_path
from tools.pipeline_eval.variants.experimental.deferred_receiver import _immutable_iq
from tools.pipeline_eval.variants.experimental.receiver_ingress import ChunkSlices, read_regular
from tools.pipeline_eval.variants.experimental.receiver_zstd_arena import DecodeArena, runtime


def _digest(data):
    return "sha256:" + sha256(data).hexdigest()


def _member(recording, path, declared_size, digest):
    data = read_regular(confined_path(recording, recording / path, must_exist=True), declared_size)
    if len(data) != declared_size or _digest(data) != digest:
        raise ValueError(f"Saved member differs from its sealed manifest: {path}")
    return data


def _chunks(recording):
    reader = ShortWindowReader(recording)
    manifest = reader.manifest
    index_type = ShortWindowIndexV2 if manifest.schema_version == 2 else ShortWindowIndexV1
    for chunk in manifest.chunks[:2]:
        if chunk.window_count != 64:
            raise ValueError("Benchmark requires complete 64-window chunks")
        index = _member(recording, chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256)
        rows = tuple(index_type.model_validate_json(line) for line in bytes(index).splitlines())
        if len(rows) != chunk.window_count:
            raise ValueError("Saved index count differs from its sealed manifest")
        offset = 0
        for position, row in enumerate(rows):
            if (
                row.sequence != chunk.first_sequence + position
                or row.payload_offset_bytes != offset
                or row.receiver_count != len(manifest.receiver_ids)
                or row.sample_count > manifest.sample_rate_hz // 50
            ):
                raise ValueError("Saved index geometry differs from its sealed manifest")
            offset += row.payload_bytes
        if offset != chunk.uncompressed_bytes:
            raise ValueError("Saved index total differs from its sealed manifest")
        compressed = _member(
            recording, chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256
        )
        yield chunk, rows, compressed


def _verify_window(full_hash, row, raw):
    if len(raw) != row.payload_bytes or _digest(raw) != row.iq_sha256:
        raise ValueError("Window length or digest changed")
    full_hash.update(raw)


def _stream(chunk, rows, compressed):
    digest = sha256()
    verification = 0.0
    start = process_time()
    with zstd.ZstdDecompressor().stream_reader(compressed) as stream:
        for row in rows:
            raw = stream.read(row.payload_bytes)
            check_start = process_time()
            _verify_window(digest, row, raw)
            verification += process_time() - check_start
        if stream.read(1):
            raise ValueError("Unexpected trailing bytes")
    decode = process_time() - start - verification
    return decode, verification, "sha256:" + digest.hexdigest()


def _arena(arena, output, chunk, rows, compressed):
    start = process_time()
    if not arena.decode(compressed, output, chunk.uncompressed_bytes):
        raise ValueError("Frame was ineligible for the candidate decoder")
    decode = process_time() - start
    check_start = process_time()
    digest = sha256()
    with memoryview(output).toreadonly() as view:
        for row in rows:
            start = row.payload_offset_bytes
            _verify_window(digest, row, view[start : start + row.payload_bytes])
    return decode, process_time() - check_start, "sha256:" + digest.hexdigest()


def _measure(operation, data):
    chunk = data[0]
    faults = getrusage(RUSAGE_SELF).ru_minflt
    wall = perf_counter()
    decode, verify, digest = operation(*data)
    if digest != chunk.uncompressed_sha256:
        raise ValueError("Decoded chunk digest changed")
    return dict(
        chunk=chunk.chunk_index,
        decode_cpu_s=decode,
        verify_cpu_s=verify,
        decode_and_verify_wall_s=perf_counter() - wall,
        minor_page_faults=getrusage(RUSAGE_SELF).ru_minflt - faults,
        decoded_sha256=digest,
    )


def _snapshot(chunk, rows, stream):
    policy = FastScanPolicyV2()
    digest = sha256()
    admitted = 0
    cpu = 0.0
    recent = deque(maxlen=32)
    for row in rows:
        raw = stream.read(row.payload_bytes)
        _verify_window(digest, row, raw)
        shape = row.sample_count, row.receiver_count, 2
        if valid_window_support(row.acquisition, 10_000_000, shape, (0, 1), policy):
            values = np.frombuffer(raw, dtype="<i2").reshape(shape)
            start = process_time()
            recent.append(_immutable_iq(values))
            cpu += process_time() - start
            admitted += 1
    if stream.read(1) or "sha256:" + digest.hexdigest() != chunk.uncompressed_sha256:
        raise ValueError("Snapshot measurement read a different chunk")
    return dict(chunk=chunk.chunk_index, admitted=admitted, snapshot_cpu_s=cpu)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--library-sha256", required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    digest = sha256(args.library.read_bytes()).hexdigest()
    if digest != args.library_sha256:
        raise ValueError("Zstandard runtime digest changed")
    library = runtime(args.library)
    compressed = tuple(_chunks(args.recording.resolve(strict=True)))
    if len(compressed) != 2:
        raise ValueError("Expected two complete chunks")
    capacity = max(chunk.uncompressed_bytes for chunk, _, _ in compressed)
    if capacity > 128 * 1024**2:
        raise ValueError("Destination arena exceeds the experimental bound")

    gc.collect()
    modes = ("stream", "direct", "stable")
    cold = {"stream": dict(setup_cpu_s=0.0, rows=[_measure(_stream, data) for data in compressed])}
    for name in modes[1:]:
        before = process_time()
        with DecodeArena(library, stable=name == "stable") as arena:
            output = np.empty(capacity, dtype=np.uint8)
            setup = process_time() - before
            op = partial(_arena, arena, output)
            cold[name] = dict(setup_cpu_s=setup, rows=[_measure(op, data) for data in compressed])
        del output, op

    before = process_time()
    output = np.empty(capacity, dtype=np.uint8)
    output.fill(0)
    with DecodeArena(library) as direct, DecodeArena(library, stable=True) as stable:
        prepare = process_time() - before
        operations = dict(
            stream=_stream,
            direct=partial(_arena, direct, output),
            stable=partial(_arena, stable, output),
        )
        warmup = {name: _measure(op, compressed[0]) for name, op in operations.items()}
        warm = []
        for repeat in range(args.repeats):
            for data in compressed if repeat % 2 == 0 else reversed(compressed):
                order = modes[repeat % len(modes) :] + modes[: repeat % len(modes)]
                for mode in order:
                    warm.append(dict(repeat=repeat, mode=mode, **_measure(operations[mode], data)))
        snapshots = []
        for repeat in range(3):
            for chunk, rows, encoded in compressed:
                with zstd.ZstdDecompressor().stream_reader(encoded) as stream:
                    snapshots.append(
                        dict(repeat=repeat, mode="stream", **_snapshot(chunk, rows, stream))
                    )
                if not direct.decode(encoded, output, chunk.uncompressed_bytes):
                    raise ValueError("Snapshot measurement could not decode a verified chunk")
                stream = ChunkSlices(memoryview(output)[: chunk.uncompressed_bytes])
                snapshots.append(
                    dict(repeat=repeat, mode="direct", **_snapshot(chunk, rows, stream))
                )

    backend = Path(find_spec("zstandard.backend_c").origin)
    print(
        json.dumps(
            dict(
                recording=str(args.recording),
                chunks=[chunk.model_dump() for chunk, _, _ in compressed],
                library_path=str(args.library),
                library_version=library.ZSTD_versionNumber(),
                library_sha256=digest,
                python_zstandard=zstd.__version__,
                python_zstd=zstd.ZSTD_VERSION,
                python_zstandard_backend_sha256=sha256(backend.read_bytes()).hexdigest(),
                frame_content_size=[zstd.frame_content_size(data[2]) for data in compressed],
                arena_bytes=capacity,
                peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
                cold=cold,
                warm_prepare_cpu_s=prepare,
                warmup=warmup,
                warm=warm,
                snapshots=snapshots,
            ),
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
