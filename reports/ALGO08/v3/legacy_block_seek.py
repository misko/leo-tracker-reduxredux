"""Decode authenticated CI16 spans of a match-free legacy Zstandard member."""

import argparse
from bisect import bisect_right
from collections import Counter
from contextlib import ExitStack, contextmanager
import ctypes as ct
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import subprocess
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.multirate_window_recording import ShortWindowIndexV2
from leo.storage import short_window
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader

from .zstd_structure import inspect, literal_section

SCHEMA = "private-legacy-zstd-block-map-v1"
PREFIX_BYTES = 80_000 * 8
WINDOW_BYTES = 200_000 * 8
MAX_MAP = 262_144
ORDERS = (("stock", "selective"), ("selective", "stock"))


def clock():
    return perf_counter_ns(), process_time_ns(), getrusage(RUSAGE_SELF).ru_inblock


def elapsed(start):
    durations = (end - begin for begin, end in zip(start, clock(), strict=True))
    return dict(zip(("wall_ns", "cpu_ns", "input_blocks"), durations, strict=True))


class UnsupportedLayout(ValueError):
    pass


class MapError(BundleCorruptionError):
    pass


def block_map(frame, expected):
    spans = []
    try:
        info = inspect(frame, expected, block_spans=spans)
    except ValueError as error:
        raise UnsupportedLayout(str(error)) from error
    if (not info["checksum"] or frame[4] & 3 or not spans or info["sequences"]
            or info["block_counts"] != {"compressed": len(spans)}
            or set(info["literal_counts"]) - {"huffman_new", "huffman_reused"}
            or not 0 < expected <= 2**32 - 1 or len(frame) > 2**32 - 1):
        raise UnsupportedLayout("requires one checksummed dictionary-free frame of Huffman blocks with zero matches")
    origin, raw_offset = None, 0
    blocks = []
    view = memoryview(frame)
    for index, (offset, length, raw_count, _) in enumerate(spans):
        mode, _, _, _, _ = literal_section(view[offset:offset + length])
        if mode == "huffman_new":
            origin = index
        if origin is None or raw_count <= 0:
            raise UnsupportedLayout("missing table origin or zero-size Huffman block")
        blocks.append([offset, length, raw_offset, raw_count, origin])
        raw_offset += raw_count
    return blocks


def identity(reader, chunk):
    return dict(manifest_sha256=reader.manifest_sha256, member_sha256=chunk.compressed_sha256,
                index_sha256=chunk.index_sha256, raw_sha256=chunk.uncompressed_sha256,
                chunk_index=chunk.chunk_index)


def seal_map(reader, chunk, frame, windows):
    # The caller exhausts the installed reader against this same compressed
    # snapshot before calling this function, including its checksum and raw SHA.
    if len(windows) != chunk.window_count:
        raise ValueError("map requires complete released decoded evidence")
    start = clock()
    blocks = block_map(frame, chunk.uncompressed_bytes)
    census = elapsed(start)
    start = clock()
    prefixes = []
    for sequence, window in enumerate(windows, chunk.first_sequence):
        if window.index.sequence != sequence:
            raise ValueError("map requires original ordered decoded windows")
        raw = memoryview(window.samples.reshape(-1)).cast("B")
        prefixes.append(sha256_digest(raw[:PREFIX_BYTES]))
    sidecar = canonical_json_bytes(dict(schema=SCHEMA, **identity(reader, chunk),
                                        blocks=blocks, prefixes=prefixes))
    return sidecar, sha256_digest(sidecar), dict(block_census=census, prefix_pins_and_seal=elapsed(start))


class Block(ct.Structure):
    _fields_ = [(name, ct.c_uint32) for name in ("encoded", "length", "decoded", "count", "origin")]


class Counts(ct.Structure):
    _fields_ = [(name, ct.c_uint64) for name in (
        "requested_blocks", "requested_encoded", "requested_decoded",
        "dependency_blocks", "dependency_encoded", "dependency_decoded")]

    def report(self):
        return {name: getattr(self, name) for name, _ in self._fields_}


def load(path):
    binary = ct.CDLL(str(path))
    binary.legacy_open.argtypes = []
    binary.legacy_open.restype = ct.c_void_p
    binary.legacy_close.argtypes = [ct.c_void_p]
    binary.legacy_close.restype = None
    binary.legacy_scratch.argtypes = [ct.c_void_p]
    binary.legacy_scratch.restype = ct.c_size_t
    binary.legacy_configure_origin.argtypes = [ct.c_void_p, ct.c_uint32, ct.c_uint32, ct.c_uint32]
    binary.legacy_configure_origin.restype = ct.c_int
    binary.legacy_origin_replays.argtypes = [ct.c_void_p]
    binary.legacy_origin_replays.restype = ct.c_uint32
    binary.legacy_span.argtypes = [
        ct.c_void_p, ct.c_char_p, ct.c_size_t, ct.POINTER(Block), ct.c_uint32, ct.c_uint32,
        ct.c_uint32, ct.c_uint32, ct.c_void_p, ct.POINTER(Counts),
    ]
    binary.legacy_span.restype = ct.c_int
    return binary


def build(destination):
    source = Path(__file__).with_suffix(".c")
    command = ["cc", "-std=c11", "-O3", "-shared", "-fPIC", "-Wall", "-Wextra",
               "-Werror", "-Wno-deprecated-declarations", str(source), "-lzstd", "-o", str(destination)]
    subprocess.run(command, check=True)
    return dict(source_sha256=sha256_digest(source.read_bytes()), binary_sha256=sha256_digest(destination.read_bytes()),
                command=command)


def read_rows(reader, chunk):
    index = reader._member(chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256)
    try:
        rows = tuple(ShortWindowIndexV2.model_validate_json(line) for line in index.splitlines())
    except ValueError as error:
        raise BundleCorruptionError("invalid original index") from error
    offset = 0
    for sequence, row in enumerate(rows, chunk.first_sequence):
        if (row.sequence != sequence or row.payload_offset_bytes != offset or row.receiver_count != 2
                or row.sample_count > 200_000 or row.payload_bytes != row.sample_count * 8):
            raise BundleCorruptionError("original index has unsupported geometry")
        offset += row.payload_bytes
    if len(rows) != chunk.window_count or offset != chunk.uncompressed_bytes:
        raise BundleCorruptionError("original index does not cover the complete member")
    return rows


def validate_map(reader, chunk, sidecar, pin):
    if len(sidecar) > MAX_MAP or sha256_digest(sidecar) != pin:
        raise MapError("detached map differs from independently pinned bytes")
    try:
        document = json.loads(sidecar)
    except ValueError as error:
        raise MapError("malformed detached map") from error
    expected = identity(reader, chunk)
    if (not isinstance(document, dict) or set(document) != {*expected, "schema", "blocks", "prefixes"}
            or document["schema"] != SCHEMA or any(document[key] != val for key, val in expected.items())):
        raise MapError("detached map does not bind the original manifest, complete member and index")
    blocks, prefixes = document["blocks"], document["prefixes"]
    if (not isinstance(blocks, list) or not blocks or not isinstance(prefixes, list)
            or len(prefixes) != chunk.window_count
            or any(not isinstance(pin, str) or len(pin) != 71 or not pin.startswith("sha256:") for pin in prefixes)):
        raise MapError("detached map omits original block or prefix coverage")
    return blocks, prefixes


class Selective:
    def __init__(self, reader, chunk, sidecar, pin, binary):
        self.binary = binary
        self.chunk = chunk
        start = clock()
        if (reader.manifest.schema_version != 2 or reader.manifest.receiver_ids != (0, 1)
                or reader.manifest.sample_rate_hz != 10_000_000
                or chunk not in reader.manifest.chunks):
            raise UnsupportedLayout("requires original signed two-antenna 10 MS/s V2 input")
        self.blocks, self.prefixes = validate_map(reader, chunk, sidecar, pin)
        self.rows = read_rows(reader, chunk)
        self.metadata = elapsed(start)
        start = clock()
        self.frame = reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
        storage = np.frombuffer(self.frame, dtype=np.uint8)
        self.pointer = ct.cast(storage.ctypes.data, ct.c_char_p)
        self.authentication = elapsed(start)
        start = clock()
        if self.blocks != block_map(self.frame, chunk.uncompressed_bytes):
            raise MapError("detached map disagrees with the authenticated frame's block structure")
        self.native_blocks = (Block * len(self.blocks))(*(Block(*row) for row in self.blocks))
        self.decoded_offsets = [row[2] for row in self.blocks]
        self.counts = Counts()
        self.context = binary.legacy_open()
        if not self.context:
            raise UnsupportedLayout("libzstd block decoder is unavailable")
        self.scratch = binary.legacy_scratch(self.context)
        self.setup = elapsed(start)

    def close(self):
        self.binary.legacy_close(self.context)

    def read(self, row, *, full):
        slot = row.sequence - self.chunk.first_sequence
        if not 0 <= slot < len(self.rows) or self.rows[slot] != row:
            raise MapError("requested row is outside the original signed index")
        length = row.payload_bytes if full else min(row.payload_bytes, PREFIX_BYTES)
        expected = row.iq_sha256 if full else self.prefixes[slot]
        result = np.empty((length // 8, 2, 2), dtype="<i2")
        if length:
            at = bisect_right(self.decoded_offsets, row.payload_offset_bytes) - 1
            if not self.binary.legacy_span(self.context, self.pointer, len(self.frame),
                                           self.native_blocks, len(self.native_blocks), at,
                                           row.payload_offset_bytes, length, result.ctypes.data, ct.byref(self.counts)):
                raise UnsupportedLayout("native libzstd block decoding declined the exact span")
        if sha256_digest(memoryview(result.reshape(-1)).cast("B")) != expected:
            raise MapError("decoded visit differs from the original complete or prefix commitment")
        result.flags.writeable = False
        return result


@contextmanager
def one_member(directory, chunk=None, *, snapshots=None):
    stock = ShortWindowReader._member

    def scoped(reader, name, size, pin):
        expected = chunk or reader.manifest.chunks[0]
        allowed = {
            expected.index_relative_path: (expected.index_bytes, expected.index_sha256),
            expected.payload_relative_path: (expected.compressed_bytes, expected.compressed_sha256),
        }
        if reader.path != directory or allowed.get(name) != (size, pin):
            raise ValueError("member access exceeds the exact staged scope")
        value = stock(reader, name, size, pin)
        if name == expected.payload_relative_path and snapshots is not None:
            snapshots.append(value)
        return value

    with patch.object(ShortWindowReader, "_member", scoped):
        yield


def missing_block(member, uses):
    """Return an encoded suffix block omitted by all requested spans and dependencies."""
    needed, active = set(), None
    for row, full in uses:
        start = row.payload_offset_bytes
        length = row.payload_bytes if full else min(row.payload_bytes, PREFIX_BYTES)
        if not length:
            continue
        first = bisect_right(member.decoded_offsets, start) - 1
        for index in range(first, len(member.blocks)):
            _, _, offset, _, origin = member.blocks[index]
            if offset >= start + length:
                break
            if active != origin:
                needed.add(origin)
                active = origin
            needed.add(index)
    for row, full in uses:
        if full:
            continue
        start = row.payload_offset_bytes + min(row.payload_bytes, PREFIX_BYTES)
        end = row.payload_offset_bytes + row.payload_bytes
        for index, (offset, size, decoded, count, _) in enumerate(member.blocks):
            if index not in needed and start <= decoded and decoded + count <= end:
                return dict(block=index, encoded_offset=offset + size // 2, sequence=row.sequence,
                            decoded_offset=decoded, omitted_blocks=len(member.blocks) - len(needed))
    raise ValueError("no genuinely skipped original short-visit suffix block")


def open_source(reader, chunk, sidecar, pin, binary):
    """An absent map stays on stock; layout declines propagate to the staged retry."""
    if sidecar is None:
        return None
    return Selective(reader, chunk, sidecar, pin, binary)


def measure(mode, scope, native, sidecar, pin, binary, evidence_rows, *, verify_words=False,
            member_index=0, open_selective=open_source):
    start = clock()
    try:
        return measure_attempt(mode, scope, native, sidecar, pin, binary, evidence_rows,
                               verify_words=verify_words, member_index=member_index, open_selective=open_selective)
    except UnsupportedLayout:
        if mode == "stock":
            raise
        timing, proof, table, uses = measure_attempt(
            "stock", scope, native, None, None, binary, evidence_rows, member_index=member_index)
        timing["fallback_including_declined_work"] = elapsed(start)
        return timing, proof, table, uses


def measure_attempt(mode, scope, native, sidecar, pin, binary, evidence_rows, *, verify_words=False,
                    member_index=0, open_selective=open_source):
    from tools.pipeline_eval.qualification.blind_compact_run import _probe, factor_candidate

    from .future_capture_storage import qualified
    from .mixed_aperture_receiver import StereoSchedule, strongest
    from .seekable_member_trial import window_from

    started = clock()
    source_pin, directory = scope.manifest, scope.path
    reader = ShortWindowReader(directory)
    if reader.manifest_sha256 != source_pin:
        raise BundleCorruptionError("original legacy manifest pin changed")
    chunk = reader.manifest.chunks[member_index]
    table = None
    if mode == "selective" and sidecar is not None:
        data = short_window.ScannerIqStore._read_regular(sidecar, MAX_MAP) if isinstance(sidecar, Path) else sidecar
        table = open_selective(reader, chunk, data, pin, binary)
    schedule = StereoSchedule(full_coverage=True)
    targets = {item["target_id"]: item for item in reader.manifest.configuration["targets"]}
    visits, probes, lanes, uses = Counter(), [], [], []
    dsp, selective_io, counts = Counter(), Counter(), {}
    with ExitStack() as stack:
        if table is not None:
            stack.callback(table.close)
            windows = ((row, None) for row in table.rows)
        else:
            windows = ((window.index, window.samples) for window in reader.windows(
                start_sequence=chunk.first_sequence, stop_sequence=chunk.first_sequence + chunk.window_count))
        for (row, samples), original in zip(windows, evidence_rows, strict=True):
            if row != original.index:
                raise ValueError("unexpected original window order")
            if not qualified(row.acquisition):
                visits["invalid"] += 1
                continue
            target = targets[row.target_id]
            _, arm = schedule.visit("lower", target, row.acquisition)
            full = arm == "full"
            visits[arm] += 1
            uses.append((row, full))
            if table is not None:
                start = clock()
                samples = table.read(row, full=full)
                selective_io.update(elapsed(start))
            if verify_words and not np.array_equal(
                    samples if full else samples[:80_000], original.samples if full else original.samples[:80_000]):
                raise ValueError("original signed CI16 span changed")
            window = window_from(row, target, samples)
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - row.acquisition["actual_if_center_hz"]
            for lane in window.receiver_ids:
                measured, (cpu, wall) = native[arm].run(samples, lane, center)
                dsp.update(cpu_ns=cpu, wall_ns=wall)
                lanes.append((row.sequence, arm, lane, measured))
                best = strongest([
                    factor_candidate(rank, epoch, status="complete", offset=offset, cfo=hz,
                                     exact=exact, control=roll, margin=exact - roll)
                    for rank, epoch, offset, hz, exact, roll in measured
                ])
                probes.append(_probe(window, lane, [best] if best is not None else []))
        if table is not None:
            counts = table.counts.report()
            if hasattr(table, "reads"):
                counts["exception_reads"] = dict(table.reads)
                counts["table_replays"] = binary.legacy_origin_replays(table.context)
    proof = dict(raw_native=canonical_digest(lanes), selected=canonical_digest(probes), lanes=len(lanes),
                 visits=dict(visits), positive_lanes=sum(bool(row["candidates"]) for row in probes),
                 residual_candidates=sum(candidate[0] != 0 for _, _, _, rows in lanes for candidate in rows))
    timing = dict(timing=elapsed(started), c_detector=dict(dsp), actual_reader="selective" if table else "stock",
                  authenticated_encoded_bytes=chunk.compressed_bytes,
                  decoded_and_committed_bytes=sum(row.payload_bytes if full else min(row.payload_bytes, PREFIX_BYTES)
                                                  for row, full in uses) if table else chunk.uncompressed_bytes,
                  selective=dict(metadata=table.metadata, complete_encoded_auth=table.authentication,
                                 structure_and_native_context=table.setup,
                                 requested_span_and_hash=dict(selective_io), native_scratch_bytes=table.scratch,
                                 **counts) if table else None)
    return timing, proof, table, uses


def corruption(reader, chunk, scope, sidecar, pin, binary, witness, ingress, *, open_selective=open_source):
    # Exercise a private mutated snapshot with the original pin, never mutate
    # the actual recording or put a waveform duplicate on disk.
    mutated = bytearray(sidecar)
    mutated[1] ^= 1
    try:
        open_selective(reader, chunk, mutated, pin, binary)
    except MapError as error:
        damaged_map = str(error)
    else:
        raise ValueError("changed map escaped authority")

    outcomes = {}
    with one_member(scope.path, chunk), ingress():
        stock = short_window.ScannerIqStore._read_regular

        def changed_source(path, bound):
            data = stock(path, bound)
            if path == reader.path / chunk.payload_relative_path:
                if not isinstance(data, memoryview) or not isinstance(data.obj, np.ndarray):
                    raise ValueError("expected a privately owned ingress buffer")
                data.obj[witness["encoded_offset"]] ^= 1
            return data

        with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(changed_source)):
            for path in ("selective", "stock"):
                try:
                    if path == "selective":
                        open_selective(reader, chunk, sidecar, pin, binary)
                    else:
                        next(reader.windows(start_sequence=chunk.first_sequence,
                                            stop_sequence=chunk.first_sequence + chunk.window_count))
                except BundleCorruptionError as error:
                    if f"short-window member changed: {chunk.payload_relative_path}" != str(error):
                        raise
                    outcomes[path] = str(error)
                else:
                    raise ValueError("changed original member escaped full compressed authentication")
    return dict(sidecar=damaged_map, omitted_suffix=witness, rejected_by=outcomes, issued_visits=0)


def run(root):
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    from . import future_capture_storage as fixture, sparse_cold_input as release
    from .full_short_run import EIGHT_MS_SHA
    from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath
    from .seekable_eight_raw import SHORT

    setting = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if (root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15 or setting != "best-effort: prio 7"):
        raise ValueError("expected isolated tmpfs output and shared CPU2/nice15/ionice7 appointment")
    root.mkdir(mode=0o700)
    library = root / "legacy-block-seek.so"
    setup = build(library)
    binary = load(library)
    policy = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    hasher = release.PAYLOAD / "paired-sha256.so"
    release.verified(hasher, policy["paired_sha256"]["sha256"])
    ingress = release.frozen_function(policy, "receiver_ingress.py", "compressed_input_buffer")
    full = release.PAYLOAD / "receiver.so"
    release.verified(full, INSTALLED_SHA)
    release.verified(SHORT, EIGHT_MS_SHA)
    pilot = np.frombuffer(release.verified(release.RELEASE / "assets/lower.f32", PILOT_SHA["lower"]), dtype="<f4")
    scope = fixture.ORIGINAL
    preparation_start = clock()
    captured = []
    with one_member(scope.path, snapshots=captured):
        reader, windows, source = fixture.verified_source(ingress, hasher, scope)
    stock_authority = elapsed(preparation_start)
    (snapshot,) = captured
    chunk = reader.manifest.chunks[0]
    start = clock()
    sidecar, pin, map_work = seal_map(reader, chunk, snapshot, windows)
    map_file = root / "map.json"
    with map_file.open("xb") as stream:
        stream.write(sidecar)
        stream.flush()
        os.fsync(stream.fileno())
    map_clock = elapsed(start)
    verify_and_build = elapsed(preparation_start)
    del snapshot, captured
    checked = None
    with ExitStack() as stack:
        native = {name: NativePath(path, pilot, name) for name, path in (
            ("full", full), ("short_primary", SHORT))}
        for engine in native.values():
            stack.callback(engine.close)
        with one_member(scope.path, chunk), ingress(), paired_decoded_hashes(hasher):
            _, checked, table, uses = measure("selective", scope, native, sidecar, pin,
                                              binary, windows, verify_words=True)
            if table is None:
                raise ValueError("verified original member did not qualify for selective decode")
            witness = missing_block(table, uses)
        del table, uses
        results = []
        for order in ORDERS:
            trial = {}
            for mode in order:
                with one_member(scope.path, chunk), ingress(), paired_decoded_hashes(hasher):
                    timing, authoritative, table, _ = measure(
                        mode, scope, native, map_file, pin, binary, windows)
                del table
                if authoritative != checked or timing["actual_reader"] != mode:
                    raise ValueError("steady-state read changed signed detector outputs or fell back")
                trial[mode] = timing
            results.append(trial)
    damage = corruption(reader, chunk, scope, sidecar, pin, binary, witness, ingress)
    blocks, _ = validate_map(reader, chunk, sidecar, pin)
    output = dict(
        source=source, stock_authority=stock_authority, sidecar_sha256=pin, sidecar_bytes=len(sidecar),
        map_clock=map_clock, verify_and_build=verify_and_build, map_work=map_work, build=setup, io_policy=setting,
        blocks=len(blocks), new_huffman_tables=sum(index == row[-1] for index, row in enumerate(blocks)),
        orders=ORDERS, ready=results, evidence=checked, corruption=damage,
        full_receiver_sha256=INSTALLED_SHA, short_receiver_sha256=EIGHT_MS_SHA,
        reader_file=ShortWindowReader.windows.__code__.co_filename,
        runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    fixture.signed.freeze(root / "result.json", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
