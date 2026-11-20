"""Read and verify bounded portions of the archived CI16 recording stream."""

from __future__ import annotations

import json
import os
import subprocess
import tracemalloc
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from statistics import median
from time import perf_counter, thread_time
from typing import BinaryIO

import numpy as np
import zstandard as zstd

from leo.contracts.multirate_window_recording import ShortWindowIndexV2, ShortWindowManifestV2
from leo.contracts.short_window_recording import ShortWindowIndexV1, ShortWindowManifestV1

MIB = 1024**2
BLOCK_BYTES = 128 * 1024
ARCHIVE_ROOT = Path("/srv/bulk/leo/fast-scan-recordings")
ROOF_PANELS = frozenset(("DS26", "DS29"))
FROZEN_INPUTS = Path(__file__).resolve().parents[1] / "frozen" / "inputs.jsonl"
MAX_CHUNK_PREFIX = 16 * MIB
MAX_DECODE_BYTES = 80 * MIB
BENCHMARK_WINDOWS = (0, 8)
REPETITIONS = 5
BOUNDARY = "short-window CI16 archive payload read, Zstd decode, and detector input assembly"


class IQReadError(ValueError):
    """A frozen IQ input could not be read and authenticated within its bounds."""


@dataclass(frozen=True)
class IQWindow:
    sequence: int
    samples: np.ndarray
    receiver_ids: tuple[int, ...]
    sample_rate_hz: int
    acquisition: dict
    target_id: str
    target: dict
    iq_sha256: str


@dataclass(frozen=True)
class ChunkPrefix:
    path: Path
    rows: tuple[ShortWindowIndexV1, ...]
    selected: frozenset[int]
    compressed_cap: int


@dataclass(frozen=True)
class IQReadPlan:
    manifest_sha256: str
    receiver_ids: tuple[int, ...]
    sample_rate_hz: int
    targets: dict[str, dict]
    prefixes: tuple[ChunkPrefix, ...]


def _digest(data: bytes | memoryview) -> str:
    return "sha256:" + sha256(data).hexdigest()


@lru_cache(maxsize=1)
def _inventory() -> dict:
    members = {}
    with FROZEN_INPUTS.open() as source:
        for line in source:
            item = json.loads(line)
            if item["panel"] in ROOF_PANELS and "recording" in item:
                members[(item["panel"], item["id"])] = item
    return members


def _recording(case: dict) -> dict:
    try:
        member = _inventory().get((case["panel"], case["id"]))
        if member is None:
            raise IQReadError("case is absent from the frozen raw IQ inventory")
        if case.get("session_id") and member["session_id"] != case["session_id"]:
            raise IQReadError("raw IQ inventory and case session IDs differ")
        return member
    except (OSError, KeyError) as error:
        raise IQReadError(f"raw IQ inventory unavailable: {error}") from error


def recording_segments(case: dict) -> tuple[dict, ...]:
    """Find the case's frozen segment locators without loading detector outputs."""
    if "recording_segments" in case:
        return tuple(case["recording_segments"] or ())
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", "/srv/bulk"))
    return tuple(
        {"path": str(bulk / entry["path"]), "sha256": "sha256:" + entry["sha256"]}
        for entry in _recording(case)["recording"]["segments"]
    )


def recording_window_count(case: dict) -> int:
    """Return the recorded window count over all segments in the acquisition."""
    if "recording_window_count" in case:
        return case["recording_window_count"]
    return _recording(case)["recording"]["window_count"]


def _locator(case: dict, segment_index: int) -> tuple[Path, str]:
    if segment_index == 0 and "recording_path" in case:
        path = case["recording_path"]
        digest = case.get("recording_sha256")
        if not path or not digest:
            raise IQReadError("recording path or frozen manifest digest is missing")
        return Path(path), digest
    segments = recording_segments(case)
    if not 0 <= segment_index < len(segments):
        raise IQReadError("requested segment is absent from the frozen raw IQ inventory")
    return Path(segments[segment_index]["path"]), segments[segment_index]["sha256"]


@contextmanager
def _bounded_file(path: Path, limit: int) -> Iterator[BinaryIO]:
    try:
        source = path.open("rb")
    except PermissionError:
        path = path.resolve()
        if not path.is_relative_to(ARCHIVE_ROOT.resolve()):
            raise
        # The corpus is owned by leo. Use the same bounded, read-only command
        # for the streamed candidate and the materialized control.
        head = ("head", "-c", str(limit), "--", str(path))
        with subprocess.Popen(
            ("timeout", "--foreground", "15s", "sudo", "-n", "-u", "leo", "--", *head),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as reader:
            assert reader.stdout is not None
            try:
                yield reader.stdout
            finally:
                reader.stdout.close()
        return
    with source:
        yield source


def _read_prefix(path: Path, limit: int) -> bytes:
    with _bounded_file(path, limit) as source:
        return source.read(limit)


def _chunk_member(root: Path, name: str) -> Path:
    if Path(name).name != name:
        raise IQReadError("IQ chunk member requires a basename")
    return root / name


def _read_plan(case: dict, sequences: Iterable[int], segment_index: int) -> IQReadPlan:
    requested = frozenset(sequences)
    if not requested or any(type(sequence) is not int or sequence < 0 for sequence in requested):
        raise IQReadError("IQ window selection requires nonnegative sequence numbers")
    path, digest = _locator(case, segment_index)
    manifest_bytes = _read_prefix(path, 64 * 1024 + 1)
    if len(manifest_bytes) > 64 * 1024 or _digest(manifest_bytes) != digest:
        raise IQReadError(f"bounded IQ segment manifest failed SHA-256 verification: {path}")
    document = json.loads(manifest_bytes)
    modern = document.get("schema_version") == 2
    manifest_type = ShortWindowManifestV2 if modern else ShortWindowManifestV1
    row_type = ShortWindowIndexV2 if modern else ShortWindowIndexV1
    manifest = manifest_type.model_validate(document)
    if path.parent.name != manifest.session_id or max(requested) >= manifest.window_count:
        raise IQReadError("IQ segment identity or requested window range differs from manifest")

    prefixes = []
    total_decoded_bytes = 0
    remaining = requested
    for chunk in manifest.chunks:
        first = chunk.first_sequence
        selected = remaining.intersection(range(first, first + chunk.window_count))
        if not selected:
            continue
        if chunk.index_bytes > MIB:
            raise IQReadError("IQ index exceeds the benchmark read budget")
        index_path = _chunk_member(path.parent, chunk.index_relative_path)
        index_bytes = _read_prefix(index_path, chunk.index_bytes + 1)
        if len(index_bytes) != chunk.index_bytes or _digest(index_bytes) != chunk.index_sha256:
            raise IQReadError(f"IQ chunk index failed SHA-256 verification: {index_path}")
        lines = index_bytes.splitlines()
        if len(lines) != chunk.window_count:
            raise IQReadError("IQ chunk index count differs from manifest")
        rows = tuple(
            row_type.model_validate_json(line) for line in lines[: max(selected) - first + 1]
        )
        offset = 0
        for sequence, row in enumerate(rows, start=first):
            if (
                row.sequence != sequence
                or row.payload_offset_bytes != offset
                or row.receiver_count != len(manifest.receiver_ids)
                or row.sample_count > manifest.sample_rate_hz // 50
                or (row.sequence in selected and row.sample_count == 0)
            ):
                raise IQReadError(f"missing IQ or invalid layout for sequence {sequence}")
            offset += row.payload_bytes
        total_decoded_bytes += offset
        if offset > MAX_CHUNK_PREFIX or total_decoded_bytes > MAX_DECODE_BYTES:
            raise IQReadError("requested IQ prefix exceeds the benchmark budget")
        cap = min(chunk.compressed_bytes, offset + MIB)
        payload_path = _chunk_member(path.parent, chunk.payload_relative_path)
        prefixes.append(ChunkPrefix(payload_path, rows, selected, cap))
        remaining = remaining - selected
    if remaining:
        raise IQReadError("requested IQ windows are missing from the recording chunks")
    targets = {target["target_id"]: target for target in manifest.configuration["targets"]}
    return IQReadPlan(
        digest, manifest.receiver_ids, manifest.sample_rate_hz, targets, tuple(prefixes)
    )


class _CompressedSource:
    def __init__(self, file: BinaryIO, cap: int):
        self.file = file
        self.cap = cap
        self.bytes_read = 0

    def read(self, size: int) -> bytes:
        block = self.file.read(min(size, self.cap - self.bytes_read))
        self.bytes_read += len(block)
        return block


def _decode(plan: IQReadPlan, *, materialize: bool) -> tuple[tuple[IQWindow, ...], int]:
    windows = []
    compressed_bytes = 0
    for prefix in plan.prefixes:
        with _bounded_file(prefix.path, prefix.compressed_cap) as source:
            bounded = _CompressedSource(source, prefix.compressed_cap)
            payload = bounded.read(prefix.compressed_cap) if materialize else bounded
            decompressor = zstd.ZstdDecompressor(max_window_size=MAX_CHUNK_PREFIX)
            with decompressor.stream_reader(payload, read_size=BLOCK_BYTES) as decoded:
                for row in prefix.rows:
                    raw = decoded.read(row.payload_bytes)
                    if len(raw) != row.payload_bytes or _digest(raw) != row.iq_sha256:
                        raise IQReadError(
                            f"short or changed IQ window {row.sequence} in {prefix.path.name}"
                        )
                    if row.sequence in prefix.selected:
                        shape = (row.sample_count, row.receiver_count, 2)
                        windows.append(
                            IQWindow(
                                sequence=row.sequence,
                                samples=np.frombuffer(raw, dtype="<i2").reshape(shape),
                                receiver_ids=plan.receiver_ids,
                                sample_rate_hz=plan.sample_rate_hz,
                                acquisition=row.acquisition,
                                target_id=row.target_id,
                                target=plan.targets[row.target_id],
                                iq_sha256=row.iq_sha256,
                            )
                        )
            compressed_bytes += bounded.bytes_read
    return tuple(windows), compressed_bytes


def load_windows(
    case: dict,
    sequences: Iterable[int] = (0, 1),
    *,
    segment_index: int = 0,
) -> tuple[IQWindow, ...]:
    """Decode authenticated segment-local windows in order as read-only CI16 arrays."""
    try:
        return _decode(_read_plan(case, sequences, segment_index), materialize=False)[0]
    except IQReadError:
        raise
    except (OSError, ValueError, KeyError, zstd.ZstdError) as error:
        raise IQReadError(f"could not read archived IQ: {error}") from error


def _equal(first: tuple[IQWindow, ...], second: tuple[IQWindow, ...]) -> bool:
    return len(first) == len(second) and all(
        control.sequence == candidate.sequence
        and control.receiver_ids == candidate.receiver_ids
        and control.samples.shape == candidate.samples.shape
        and control.samples.dtype == candidate.samples.dtype
        and memoryview(control.samples).cast("B") == memoryview(candidate.samples).cast("B")
        for control, candidate in zip(first, second, strict=True)
    )


def _memory(plan: IQReadPlan, materialize: bool) -> int:
    tracemalloc.start()
    try:
        _decode(plan, materialize=materialize)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _helper_cpu_s() -> float:
    usage = getrusage(RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def run(case: dict, work_dir: Path) -> dict:
    """Run five alternating pairs on the same two authenticated roof windows."""
    del work_dir
    try:
        if case.get("panel") not in ROOF_PANELS:
            raise IQReadError("no archived short-window CI16 input for this panel")
        plan = _read_plan(case, BENCHMARK_WINDOWS, 0)
        pairs = {True: [], False: []}
        parity = True
        for number in range(REPETITIONS):
            decoded = {}
            for materialize in (True, False) if number % 2 == 0 else (False, True):
                start_wall, start_cpu, start_helper = perf_counter(), thread_time(), _helper_cpu_s()
                windows, bytes_read = _decode(plan, materialize=materialize)
                cpu, wall = thread_time() - start_cpu, perf_counter() - start_wall
                pairs[materialize].append((wall, cpu, _helper_cpu_s() - start_helper, bytes_read))
                decoded[materialize] = windows
            parity &= _equal(decoded[True], decoded[False])

        result = {
            "paired_repetitions": REPETITIONS,
            "window_sequences": list(BENCHMARK_WINDOWS),
            "windows": len(windows),
            "samples_per_receiver": sum(len(window.samples) for window in windows),
            "receiver_ids": list(plan.receiver_ids),
            "sample_rate_hz": plan.sample_rate_hz,
            "decoded_prefix_bytes": sum(
                row.payload_bytes for prefix in plan.prefixes for row in prefix.rows
            ),
            "decoded_prefix_windows": sum(len(prefix.rows) for prefix in plan.prefixes),
            "detector_ci16_bytes": sum(window.samples.nbytes for window in windows),
            "manifest_sha256": plan.manifest_sha256,
            "detector_iq_sha256": [window.iq_sha256 for window in windows],
            "bitwise_equal": parity,
            "candidate_compressed_block_bytes": BLOCK_BYTES,
        }
        for name, materialize in (("control", True), ("candidate", False)):
            wall, cpu, helper_cpu, read_bytes = map(list, zip(*pairs[materialize], strict=True))
            result.update(
                {
                    f"{name}_s": median(wall),
                    f"{name}_cpu_s": median(cpu),
                    f"{name}_archive_helper_cpu_s": median(helper_cpu),
                    f"{name}_wall_repeats_s": wall,
                    f"{name}_cpu_repeats_s": cpu,
                    f"{name}_compressed_read_bytes": read_bytes,
                    f"{name}_traced_peak_bytes": _memory(plan, materialize),
                }
            )
        result["cpu_scope"] = "decoder thread and archive read helper reported separately"
        result["memory_scope"] = "Python/NumPy allocations, excluding native Zstd and read helper"
        return {"status": "ok", "boundary": BOUNDARY, "metrics": result}
    except (OSError, ValueError, KeyError, zstd.ZstdError) as error:
        return {"status": "unavailable", "boundary": BOUNDARY, "reason": str(error), "metrics": {}}
