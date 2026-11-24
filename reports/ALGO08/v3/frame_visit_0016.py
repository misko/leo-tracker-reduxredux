"""One-member independent qualification of chronological visit frames."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager, nullcontext
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import zstandard as zstd

from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.multirate_window_recording import ShortWindowChunkV2, ShortWindowIndexV2
from leo.storage import short_window
from leo.storage.errors import BundleCorruptionError
from leo.storage.writer import _CompressedFileWriter, _DigestingSink, _fsync_directory

from . import future_capture_storage as fixture, sparse_cold_input as frozen
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, StereoSchedule, strongest
from .owned_capture_0016 import logical, ordinary_capture
from .seekable_member_trial import clock, elapsed, window_from

SCHEMA = "private-zstd-visit-frames-8ms-v1"
SIDE = "visit-frames.json"
PREFIX_BYTES = 80_000 * 8
MAX_SIDE_BYTES = 256_000
MAX_SCRATCH = 300_000_000
ORDERS = (("ordinary", "frames"), ("frames", "ordinary"))


class VisitFrames(_CompressedFileWriter):
    """Alternate payload backend, leaving the released writer's index/seal intact."""

    def __init__(self, filename, level, records):
        self.partial_path, self.final_path = filename, filename.with_suffix("")
        self._raw = filename.open("xb")
        self._sink = _DigestingSink(self._raw)
        self._compressor = zstd.ZstdCompressor(level=level, write_checksum=True)
        self._closed = False
        self.records = records

    def write(self, raw):
        offset = self._sink.byte_count
        count = min(len(raw), PREFIX_BYTES)
        prefix = raw[:count]
        if raw:
            op = self._compressor.compressobj(size=len(raw))
            self._sink.write(op.compress(prefix))
            self._sink.write(op.flush(zstd.COMPRESSOBJ_FLUSH_BLOCK))
        prefix_end = self._sink.byte_count
        if raw:
            self._sink.write(op.compress(raw[count:]))
            self._sink.write(op.flush())
        self.records.append(dict(sequence=len(self.records), offset=offset,
                                 frame_bytes=self._sink.byte_count - offset,
                                 prefix_end=prefix_end, prefix_bytes=count,
                                 prefix_sha256=sha256_digest(prefix)))

    def finish(self):
        if not self._sink.byte_count:
            self._sink.write(self._compressor.compress(b""))
        self._raw.flush()
        os.fsync(self._raw.fileno())
        self.abort()
        os.replace(self.partial_path, self.final_path)
        _fsync_directory(self.final_path.parent)
        return self.final_path, self._sink.byte_count, self._sink.digest

    def abort(self):
        self._raw.close()
        self._closed = True


def write_capture(directory, header, windows, mode):
    records = []

    def alternate(filename, *, level):
        return VisitFrames(filename, level, records)

    with (patch.object(short_window, "_CompressedFileWriter", alternate)
          if mode == "frames" else nullcontext()):
        pin, (chunk,) = ordinary_capture(directory, header, windows)
    side_pin = None
    if mode == "frames":
        sidecar = canonical_json_bytes(dict(
            schema=SCHEMA, manifest_sha256=pin, index_sha256=chunk["index_sha256"],
            compressed_sha256=chunk["compressed_sha256"], records=records,
        ))
        with (directory / SIDE).open("xb") as stream:
            stream.write(sidecar)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(directory)
        side_pin = sha256_digest(sidecar)
    return pin, side_pin, chunk


def bound_chunk(reader, chunk):
    chunks = reader.manifest.chunks
    if chunk is None and len(chunks) == 1:
        chunk = chunks[0]
    if (not isinstance(chunk, ShortWindowChunkV2) or not 0 <= chunk.chunk_index < len(chunks)
            or chunk != chunks[chunk.chunk_index]):
        raise BundleCorruptionError("visit table requires a chunk bound to the installed manifest")
    return chunk


def read_table(reader, pin, *, chunk=None, side_name=SIDE):
    """Accept one externally pinned table for the declared segment member."""
    chunk = bound_chunk(reader, chunk)
    if (not isinstance(side_name, str) or not side_name or side_name in (".", "..")
            or Path(side_name).name != side_name):
        raise BundleCorruptionError("visit sidecar name must stay inside the segment")
    path = reader.path / side_name
    data = short_window.ScannerIqStore._read_regular(path, MAX_SIDE_BYTES)
    if sha256_digest(data) != pin:
        raise BundleCorruptionError("visit sidecar differs from its frozen pin")
    document = json.loads(data)
    if (not isinstance(document, dict) or set(document) != {
            "schema", "manifest_sha256", "index_sha256", "compressed_sha256", "records"}
            or [document[key] for key in ("schema", "manifest_sha256", "index_sha256",
                                         "compressed_sha256")] != [
                SCHEMA, reader.manifest_sha256, chunk.index_sha256, chunk.compressed_sha256]
            or not isinstance(document["records"], list)
            or len(document["records"]) != chunk.window_count
            or reader.manifest.schema_version != 2 or reader.manifest.receiver_ids != (0, 1)
            or reader.manifest.sample_rate_hz != 10_000_000):
        raise BundleCorruptionError("visit sidecar identity or geometry differs from the member")
    offset = 0
    for sequence, record in enumerate(document["records"], start=chunk.first_sequence):
        names = ("sequence", "offset", "frame_bytes", "prefix_end", "prefix_bytes")
        if (not isinstance(record, dict) or set(record) != {*names, "prefix_sha256"}
                or any(type(record[key]) is not int for key in names)):
            raise BundleCorruptionError("invalid visit-frame record fields")
        finish = offset + record["frame_bytes"]
        if (record["sequence"] != sequence or record["offset"] != offset
                or not offset <= record["prefix_end"] <= finish <= chunk.compressed_bytes
                or not 0 <= record["prefix_bytes"] <= PREFIX_BYTES
                or bool(record["frame_bytes"]) != bool(record["prefix_bytes"])
                or bool(record["prefix_end"] - offset) != bool(record["prefix_bytes"])):
            raise BundleCorruptionError("visit-frame extents do not form a consecutive partition")
        offset = finish
    # The released index requires a positive encoded member, even for all-empty visits.
    if offset != chunk.compressed_bytes and (offset or chunk.uncompressed_bytes):
        raise BundleCorruptionError("visit frames do not cover the encoded member")
    return document["records"], len(data)


def check_raw(raw, count, pin):
    if len(raw) != count or sha256_digest(raw) != pin:
        raise BundleCorruptionError("decoded visit extent or digest changed")


class SelectiveMember:
    """Verify the whole encoded file before exposing any checked decoded span."""

    def __init__(self, reader, side_pin, *, chunk=None, side_name=SIDE):
        self.reader = reader
        self.chunk = bound_chunk(reader, chunk)
        stage = clock()
        self.records, side_bytes = read_table(reader, side_pin, chunk=self.chunk, side_name=side_name)
        data = reader._member(self.chunk.index_relative_path, self.chunk.index_bytes, self.chunk.index_sha256)
        self.rows = [ShortWindowIndexV2.model_validate_json(line) for line in data.splitlines()]
        offset = 0
        if len(self.rows) != len(self.records):
            raise BundleCorruptionError("visit index count differs from its frame table")
        for row, record in zip(self.rows, self.records, strict=True):
            if (row.sequence != record["sequence"] or row.payload_offset_bytes != offset
                    or row.receiver_count != 2 or row.sample_count > 200_000
                    or row.payload_bytes != row.sample_count * 8
                    or record["prefix_bytes"] != min(row.payload_bytes, PREFIX_BYTES)):
                raise BundleCorruptionError("visit index disagrees with frame geometry")
            offset += row.payload_bytes
        if offset != self.chunk.uncompressed_bytes:
            raise BundleCorruptionError("visit index does not cover the decoded member")
        self.metadata = elapsed(stage)
        stage = clock()
        self.encoded = memoryview(reader._member(
            self.chunk.payload_relative_path, self.chunk.compressed_bytes, self.chunk.compressed_sha256))
        self.authentication = elapsed(stage)
        self.decoder = zstd.ZstdDecompressor()
        if not offset and (zstd.frame_content_size(self.encoded) != 0
                           or self.decoder.decompress(self.encoded, allow_extra_data=False)):
            raise BundleCorruptionError("all-empty visit member decodes to nonempty CI16")
        self.counts = Counter(metadata_bytes=side_bytes + len(data) + (reader.path/"manifest.json").stat().st_size,
                              authenticated_encoded_bytes=len(self.encoded))

    def read(self, row, *, full):
        index = row.sequence - self.chunk.first_sequence
        if not 0 <= index < len(self.rows) or row != self.rows[index]:
            raise BundleCorruptionError("requested visit is outside the verified chunk index")
        record = self.records[index]
        start = record["offset"]
        if full:
            end = start + record["frame_bytes"]
            frame = self.encoded[start:end]
            raw = b""
            if frame:
                if zstd.frame_content_size(frame) != row.payload_bytes:
                    raise BundleCorruptionError("frame content size conflicts with the sealed index")
                raw = self.decoder.decompress(frame, allow_extra_data=False)
            check_raw(raw, row.payload_bytes, row.iq_sha256)
        else:
            end = record["prefix_end"]
            raw = b""
            if end > start:
                with self.decoder.stream_reader(self.encoded[start:end]) as stream:
                    raw = stream.read(record["prefix_bytes"] + 1)
            check_raw(raw, record["prefix_bytes"], record["prefix_sha256"])
        self.counts["decoded_bytes"] += len(raw)
        self.counts["encoded_bytes_fed_to_decoder"] += end - start
        self.counts["full_checks" if full else "prefix_checks"] += 1
        return np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)


class Mode(Enum):
    COMPLETE_MIXED = "complete-mixed"
    SELECTIVE_MIXED = "selective-mixed"
    COMPLETE_FULL = "complete-full"


def measure_read(directory, pin, side_pin, windows, native, mode, *, compare_words=False):
    from tools.pipeline_eval.qualification.blind_compact_run import _probe, factor_candidate

    started = clock()
    reader = short_window.ShortWindowReader(directory)
    if reader.manifest_sha256 != pin:
        raise BundleCorruptionError("fresh capture manifest changed")
    (chunk,) = reader.manifest.chunks
    selective = mode is Mode.SELECTIVE_MIXED
    source = SelectiveMember(reader, side_pin) if selective else None
    table = read_table(reader, side_pin)[0] if side_pin and not selective else None
    targets = {row["target_id"]: row for row in reader.manifest.configuration["targets"]}
    schedule = StereoSchedule(full_coverage=True)
    iter_windows = ((row, None) for row in source.rows) if source else (
        (visit.index, visit.samples) for visit in reader.windows())
    probes, raw_lanes, visits, c_time = [], [], Counter(), Counter()
    comparison, materialize = Counter(), Counter()
    for own, (row, samples) in zip(windows, iter_windows, strict=True):
        start = clock()
        if row != own.index:
            raise BundleCorruptionError("installed readback changed a stored row or order")
        if samples is not None:
            if compare_words and not np.array_equal(samples, own.samples):
                raise BundleCorruptionError("installed readback changed owned CI16")
            if table is not None:
                prefix = memoryview(samples.reshape(-1)).cast("B")[:PREFIX_BYTES]
                record = table[row.sequence]
                check_raw(prefix, record["prefix_bytes"], record["prefix_sha256"])
        comparison.update(elapsed(start))
        target = targets[row.target_id]
        if not fixture.qualified(row.acquisition):
            visits["invalid"] += 1
            continue
        which = "full"
        if mode is not Mode.COMPLETE_FULL:
            _, which = schedule.visit("lower", target, row.acquisition)
        visits[which] += 1
        if source is not None:
            begin = clock()
            samples = source.read(row, full=which == "full")
            materialize.update(elapsed(begin))
        window = window_from(row, target, samples)
        center = target["rf_center_hz"] - target["lnb_lo_hz"] - row.acquisition["actual_if_center_hz"]
        for lane in window.receiver_ids:
            measured, (cpu, wall) = native[which].run(samples, lane, center)
            c_time.update(cpu_ns=cpu, wall_ns=wall)
            raw_lanes.append((row.sequence, which, lane, measured))
            candidates = [
                factor_candidate(rank, epoch, status="complete", offset=offset, cfo=hz,
                                 exact=exact, control=roll, margin=exact - roll)
                for rank, epoch, offset, hz, exact, roll in measured
            ]
            best = strongest(candidates)
            probes.append(_probe(window, lane, [best] if best is not None else []))
    result = dict(timing=elapsed(started), c_detector=dict(c_time), compare_owned_rows_and_words=dict(comparison),
                  selective_metadata=source.metadata if source else None,
                  selective_complete_encoded_authentication=source.authentication if source else None,
                  selective_decoding=dict(materialize) if source else None,
                  reads=dict(source.counts) if source else dict(
                      decoded_bytes=chunk.uncompressed_bytes, full_checks=chunk.window_count,
                      authenticated_encoded_bytes=chunk.compressed_bytes,
                      encoded_bytes_fed_to_decoder=chunk.compressed_bytes))
    evidence = dict(visits=dict(visits), lanes=len(raw_lanes), raw_native=canonical_digest(raw_lanes),
                    short_sequences=[sequence for sequence, which, lane, _ in raw_lanes
                                     if which == "short_primary" and lane == 0],
                    selected=canonical_digest(probes), positives=sum(bool(row["candidates"]) for row in probes),
                    cancellation_candidates=sum(1 for _, _, _, lane in raw_lanes
                                                for candidate in lane if candidate[0] != 0))
    return result, evidence


@contextmanager
def changed_byte(path, offset):
    with path.open("r+b") as stream:
        stream.seek(offset)
        original = stream.read(1)
        if len(original) != 1:
            raise ValueError("no byte at the corruption witness offset")
        stream.seek(offset)
        stream.write(bytes((original[0] ^ 1,)))
        stream.flush()
        try:
            yield
        finally:
            stream.seek(offset)
            stream.write(original)
            stream.flush()


def refusal(path, side_pin, chunk, *, short_sequence=None):
    reader = short_window.ShortWindowReader(path)
    if short_sequence is None:
        damaged, offset = path / SIDE, 1
    else:
        records, _ = read_table(reader, side_pin)
        record = records[short_sequence]
        suffix_length = record["offset"] + record["frame_bytes"] - record["prefix_end"]
        if suffix_length <= 8:
            raise ValueError("need a short-visit encoded suffix beyond the prefix block")
        damaged, offset = path / chunk["payload_relative_path"], record["prefix_end"] + suffix_length // 2
    with changed_byte(damaged, offset):
        try:
            SelectiveMember(reader, side_pin)
        except BundleCorruptionError as error:
            message = str(error)
            if ("visit sidecar" if short_sequence is None else chunk["payload_relative_path"]) not in message:
                raise
        else:
            raise ValueError("corruption escaped strict admission")
        if short_sequence is not None:
            try:
                next(reader.windows())
            except BundleCorruptionError as error:
                if message != str(error):
                    raise
            else:
                raise ValueError("installed reader exposed data before rejecting the changed member")
    return dict(file=damaged.name, offset=offset, rejected=message, issued_visits=0,
                scheduled_short_sequence=short_sequence)


def qualification(result_path):
    from .full_short_run import EIGHT_MS_SHA
    from .seekable_eight_raw import SHORT
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    if (result_path.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15
            or not Path(short_window.__file__).is_relative_to(frozen.RELEASE / "src")):
        raise ValueError("use a fresh tmpfs receipt, CPU2/nice15 and the installed short-window code")
    io_policy = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if io_policy != "best-effort: prio 7":
        raise ValueError("expected ionice class 2 priority 7")
    scope = json.loads(frozen.verified(frozen.PAYLOAD/"spec.json", frozen.SPEC_SHA))
    full = frozen.PAYLOAD / "receiver.so"
    frozen.verified(full, INSTALLED_SHA)
    frozen.verified(SHORT, EIGHT_MS_SHA)
    pilot = np.frombuffer(frozen.verified(frozen.RELEASE/"assets/lower.f32", PILOT_SHA["lower"]), dtype="<f4")
    hasher = frozen.PAYLOAD / "paired-sha256.so"
    frozen.verified(hasher, scope["paired_sha256"]["sha256"])
    ingress = frozen.frozen_function(scope, "receiver_ingress.py", "compressed_input_buffer")
    original, windows, source = fixture.verified_source(ingress, hasher)
    if any(window.index.sequence != i or window.samples.flags.writeable for i, window in enumerate(windows)):
        raise ValueError("expected complete chronological immutable owned CI16")
    output = dict(source=source, full_sha256=INSTALLED_SHA, eight_sha256=EIGHT_MS_SHA,
                  pilot_sha256=PILOT_SHA["lower"], zstd_version=zstd.ZSTD_VERSION,
                  reader_sha256=sha256(Path(short_window.__file__).read_bytes()).hexdigest(),
                  runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  cpu_affinity=sorted(os.sched_getaffinity(0)), nice=os.getpriority(os.PRIO_PROCESS, 0),
                  ionice=io_policy, ready_orders=ORDERS, captures={}, complete_twenty={}, ready=[])
    with TemporaryDirectory(dir="/dev/shm", prefix="visit-frame-0016-") as temporary, ExitStack() as stack:
        native = {name: NativePath(binary, pilot, name) for name, binary in
                  (("full", full), ("short_primary", SHORT))}
        for engine in native.values():
            stack.callback(engine.close)
        paths, expected = {}, {}
        for arm in ORDERS[0]:
            path = Path(temporary) / arm
            begin = clock()
            pin, side_pin, chunk = write_capture(path, original.manifest, windows, arm)
            write = elapsed(begin)
            scan, evidence = measure_read(path, pin, side_pin, windows, native,
                                          Mode.COMPLETE_MIXED, compare_words=True)
            both = elapsed(begin)
            paths[arm] = path, pin, side_pin, chunk
            expected[arm] = evidence
            files = {item.name: item.stat().st_size for item in path.iterdir()}
            output["captures"][arm] = dict(
                timing=write, first_independent_read_and_mixed_detection=scan, capture_to_first=both,
                bytes=files, manifest_sha256=pin, sidecar_sha256=side_pin, chunk=chunk)
            if logical([chunk]) != logical([original.manifest.chunks[0].model_dump(mode="json")]):
                raise ValueError("new capture altered original logical source identity")
        if expected["ordinary"] != expected["frames"]:
            raise ValueError("physical archive changed mixed receiver output")
        output["scratch_bytes"] = sum(sum(arm["bytes"].values()) for arm in output["captures"].values())
        if output["scratch_bytes"] > MAX_SCRATCH:
            raise ValueError("one-member capture exceeded its scratch scope")
        output["mixed_evidence"] = expected["ordinary"]
        for order in ORDERS:
            result = {}
            for arm in order:
                path, pin, side_pin, _ = paths[arm]
                mode = Mode.SELECTIVE_MIXED if arm == "frames" else Mode.COMPLETE_MIXED
                with ingress(), paired_decoded_hashes(hasher):
                    metrics, evidence = measure_read(path, pin, side_pin, windows, native, mode)
                if evidence != expected["ordinary"]:
                    raise ValueError("ready member changed full, short or empty signed lane output")
                result[arm] = metrics
            output["ready"].append(result)
        all_twenty = None
        for arm, (path, pin, side_pin, _) in paths.items():
            read, evidence = measure_read(path, pin, side_pin, windows, native, Mode.COMPLETE_FULL)
            if all_twenty is not None and evidence != all_twenty:
                raise ValueError("physical archive changed all-20 ms receiver output")
            all_twenty = evidence
            output["complete_twenty"][arm] = read
        output["all_twenty_evidence"] = all_twenty
        path, _, side_pin, chunk = paths["frames"]
        output["corrupt_sidecar"] = refusal(path, side_pin, chunk)
        output["corrupt_unused_suffix"] = refusal(
            path, side_pin, chunk, short_sequence=expected["frames"]["short_sequences"][0])
    fixture.signed.freeze(result_path, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    qualification(parser.parse_args().receipt)
