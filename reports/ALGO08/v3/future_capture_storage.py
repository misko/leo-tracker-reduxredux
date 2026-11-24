"""Price a sealed capture plus first mixed use on the resident physical member."""

import argparse
from collections import Counter
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import zstandard as zstd
from unittest.mock import patch

from . import full_short_cold as signed
from . import seekable_member as seek
from . import sparse_cold_input as frozen
from .mixed_aperture_receiver import MixedApertureDetector, NativePath, StereoSchedule
from .seekable_member_trial import clock, elapsed, mixed_call, window_from


SOURCE = Path("/dev/shm/leo-v3-guarded-selective-0016-stage01") / (
    "fast8-auto-20261113-112146-b04f5461-1-lower/"
    "fast8-auto-20261113-112146-b04f5461-1-lower-segment-00000000")
MANIFEST = "sha256:1530e4a7376f569f52d2b41dfdfc732489b036df73a8cff9b0feabecbc8cb3cc"
COMPRESSED = "sha256:4773bee9d16a0291338408540c4b4e83c6ce960bb2ed01ef1e5e65a25d38ea4a"
DECODED = "sha256:defed2edfa130b9c1cbee028b9c5daa3700265a9bc2ecc1d0b5105fc67089b43"
INDEX = "sha256:dfe2b6d4971a48811462a2ad1f97e85a7574fa949c0b8f10fe4222e0ab20c609"
SHORT = Path("/dev/shm/leo-v3-raw-0016-best-results-01/short.so")
LEVELS = {"ordinary": 1, "split-level-1": 1, "split-level-fast": -1}
ORDERS = (tuple(LEVELS), ("split-level-fast", "ordinary", "split-level-1"),
          ("split-level-1", "split-level-fast", "ordinary"))
MATCH = ("timeline_sha256", "probes_sha256", "issued", "admitted", "invalid", "visits", "selected")


@dataclass(frozen=True)
class StagedMember:
    case: str
    path: Path
    manifest: str
    compressed: str
    decoded: str
    index: str
    compressed_bytes: int
    index_bytes: int
    manifest_bytes: int
    prior_probes: str | None = None


ORIGINAL = StagedMember("DS30-0016", SOURCE, MANIFEST, COMPRESSED, DECODED, INDEX, 78_554_951, 173_091, 6_812)


class ApertureWriter:
    """The existing capture writer's private payload backend for one seek table."""

    def __init__(self, filename, level, records, costs, codec=None, prefix_samples=seek.PREFIX_SAMPLES):
        self.paths = [filename.parent / name for name in seek.part_files(codec)]
        _, self.extents = seek.layout(prefix_samples, codec)
        self.compressor = zstd.ZstdCompressor(level=level, write_checksum=True) if codec is None else codec
        with ExitStack() as stack:
            self.files = [stack.enter_context(path.open("xb")) for path in self.paths]
            self.streams = stack.pop_all()
        self.records, self.costs = records, costs
        self.prefix = sha256()

    def write(self, chunk):
        if len(chunk) != seek.WINDOW_BYTES:
            raise ValueError("Expected one complete capture window")
        parts = []
        chunks = chunk[:self.extents[0]], chunk[self.extents[0]:]
        for stream, raw in zip(self.files, chunks, strict=True):
            start = clock()
            encoded = self.compressor.compress(raw)
            parts.append([stream.tell(), len(encoded), seek.digest(encoded), seek.digest(raw)])
            self.costs["split_encode_and_hash_cpu_ns"] += elapsed(start)["cpu_ns"]
            stream.write(encoded)
            if stream is self.files[0]:
                self.prefix.update(encoded)
        self.records.append(dict(sequence=len(self.records), parts=parts))

    def finish(self):
        try:
            for stream in self.files:
                stream.flush()
                os.fsync(stream.fileno())
            size = self.files[0].tell()
        finally:
            self.streams.close()
        for path in self.paths:
            path.chmod(0o400)
        return self.paths[0], size, "sha256:" + self.prefix.hexdigest()

    def abort(self):
        self.streams.close()


def capture(root, mode, template, windows, *, codec=None, prefix_samples=seek.PREFIX_SAMPLES):
    from leo.storage import short_window
    from leo.storage.writer import _fsync_directory

    records, costs = [], Counter()
    def factory(filename, *, level):
        return ApertureWriter(filename, level, records, costs, codec=codec, prefix_samples=prefix_samples)

    split = mode != "ordinary"
    if not split and codec is not None:
        raise ValueError("An independent codec requires the split capture layout")
    level = LEVELS[mode] if codec is None else None
    start = clock()
    writer = short_window.ShortWindowWriter(root, "capture", configuration=template.configuration,
                                          radio=template.radio, receiver_ids=template.receiver_ids,
                                          chunk_windows=len(windows), compression_level=level if level is not None else 1,
                                          schema_version=2)
    try:
        # Reuse production CI16, metadata, per-window and whole SHA, and durable
        # sealing. The temporary root is private until the seek commit exists.
        with patch.object(short_window, "_CompressedFileWriter", factory) if split else nullcontext():
            for window in windows:
                row = window.index
                writer.append(sequence=row.sequence, target_id=row.target_id, samples=window.samples,
                              acquisition=row.acquisition, powers=row.powers)
            directory = writer.finish(stop_reason="bounded physical capture emulator")
    except BaseException:
        writer.abort()
        raise
    manifest = directory / "manifest.json"
    manifest_bytes = manifest.read_bytes()
    pin = seek.digest(manifest_bytes)
    header = seek.ShortWindowManifestV2.model_validate_json(manifest_bytes)
    (chunk,) = header.chunks
    if split:
        if len(records) != len(windows):
            raise ValueError("Split encoder returned incomplete capture coverage")
        manifest.rename(directory / "source-manifest.json")
        (directory / chunk.index_relative_path).rename(directory / "source-index.jsonl")
        schema, _ = seek.layout(prefix_samples, codec)
        document = dict(schema=schema, original_manifest=pin,
                        original_index=chunk.index_sha256,
                        chunk_index=0, records=records)
        seal = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        seek.write(directory / "seek.json", seal)
        _fsync_directory(directory)
        pin = seek.digest(seal)
    result = elapsed(start) | dict(costs)
    sizes = {path.name: path.stat().st_size for path in directory.iterdir()}
    return directory, pin, dict(timing=result, bytes=sizes, total_bytes=sum(sizes.values()), root_sha256=pin,
                                index_sha256=chunk.index_sha256, decoded_sha256=chunk.uncompressed_sha256,
                                manifest_compressed_sha256=chunk.compressed_sha256,
                                manifest_compressed_scope="prefix file" if split else "complete member",
                                compression_level=level)


def verified_source(ingress, hasher, member=ORIGINAL):
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    source = member.path
    if (not source.is_relative_to("/dev/shm") or source.resolve(strict=True) != source
            or source.stat().st_dev != Path("/dev/shm").stat().st_dev):
        raise ValueError("Expected a pinned local tmpfs member")
    frozen.verified(frozen.CACHE_LIBRARY, frozen.CACHE_SHA)
    query = load_query(frozen.CACHE_LIBRARY)
    members = (("manifest.json", member.manifest_bytes), ("windows-000000.jsonl", member.index_bytes),
               ("iq-000000.ci16.zst", member.compressed_bytes))
    if any((source / name).resolve(strict=True) != source / name or (source / name).stat().st_size != size
           for name,size in members):
        raise ValueError("Pinned source file extents changed")
    cache = cache_snapshot([(source, name, size) for name,size in members], os.sysconf("SC_PAGE_SIZE"), query)
    if (cache["unavailable"] or cache["observed_members"] != len(members)
            or cache["cached_pages"] != cache["observed_file_pages"]):
        raise ValueError("All 64 source visits must be resident before decoding")
    start = clock()
    reader = ShortWindowReader(source)
    chunk = reader.manifest.chunks[0]
    if (reader.manifest_sha256, chunk.compressed_sha256, chunk.uncompressed_sha256,
            chunk.index_sha256, chunk.first_sequence, chunk.window_count) != (
                member.manifest, member.compressed, member.decoded, member.index, 0, 64):
        raise ValueError("Source manifest does not bind the exact signed samples")
    with ingress(), paired_decoded_hashes(hasher):
        windows = list(reader.windows(start_sequence=0, stop_sequence=64))
    if (len(windows) != 64 or any(row.samples.shape != (seek.SAMPLES, 2, 2) for row in windows)):
        raise ValueError("Fixture capture is not a full stereo 64-visit member")
    return reader, windows, dict(timing=elapsed(start), cache=cache, raw_bytes=chunk.uncompressed_bytes,
                                 source=str(source), case=member.case, manifest=member.manifest, compressed=member.compressed,
                                 decoded=member.decoded, index=member.index, prior_probes=member.prior_probes)


def qualified(acquisition):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support

    return valid_window_support(acquisition, 10_000_000, (seek.SAMPLES, 2, 2), (0, 1), FastScanPolicyV2())


def analyze(directory, mode, pin, full, short, pilot, ingress, hasher, *, codec=None):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    probes, timeline, counts = [], [], Counter()
    start = clock()
    split = mode != "ordinary"
    native = Counter()
    with ExitStack() as stack:
        if split:
            reader = stack.enter_context(seek.open_member(directory, pin, codec=codec))
            verify_started = clock()
            reader.verify_encoded()
            compressed_check = elapsed(verify_started)
            rows = reader.rows
            target_map = {target["target_id"]: target for target in reader.manifest.configuration["targets"]}
            windows = ((row.sequence, row.iq_sha256, row.acquisition, target_map[row.target_id], None) for row in rows)
            schedule = StereoSchedule(full_coverage=True)
            asset = np.frombuffer(frozen.verified(pilot, signed.PILOT_SHA["lower"]), dtype="<f4")
            engines = {}
            for label, binary in (("full", full), ("short_primary", short)):
                engines[label] = NativePath(binary, asset, label)
                stack.callback(engines[label].close)
        else:
            compressed_check = None
            original = FastSegmentSource(dict(path=str(directory), manifest_digest=pin))
            stack.enter_context(ingress())
            stack.enter_context(paired_decoded_hashes(hasher))
            engine = MixedApertureDetector(short, signed.SHORT_SHA, full_coverage=True)
            callback = stack.enter_context(engine.detector("cancellation", "lower", binary=full, pilot=pilot))
            windows = ((row.sequence, row.iq_sha256, row.acquisition, row.target, row) for row in original.windows())

        for sequence, iq_sha, acquisition, target, original_window in windows:
            admit = qualified(acquisition)
            timeline.append((sequence, iq_sha, acquisition, target, admit))
            if not admit:
                counts["invalid"] += 1
                continue
            if target["edge"] != "lower":
                raise ValueError("Frozen DS30-0016 fixture expects its lower pilot edge")
            if split:
                _, aperture = schedule.visit("lower", target, acquisition)
                counts[aperture] += 1
                raw = reader.read(sequence, full=aperture == "full")
                window = window_from(rows[sequence], target, np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2))
                begin = clock()
                probes.extend(mixed_call(engines[aperture], window))
            else:
                window = window_from(original_window, target, original_window.samples)
                begin = clock()
                probes.extend(callback(window))
            native.update(elapsed(begin))
        if split:
            reads = reader.counts() | {"verified_encoded_frames": reader.verified_encoded_frames}
            visits = {label: counts[label] for label in ("full", "short_primary")}
        else:
            chunk = original.reader.manifest.chunks[0]
            reads = dict(payload_bytes=chunk.compressed_bytes, decoded_bytes=chunk.uncompressed_bytes,
                         metadata_bytes=chunk.index_bytes + (directory / "manifest.json").stat().st_size,
                         frames=1, full_checks=chunk.window_count, verified_encoded_frames=1)
            visits = {label: engine.visits[label] for label in ("full", "short_primary")}
    return dict(timing=elapsed(start), native=dict(native), compressed_verification=compressed_check,
                timeline_sha256=canonical_digest(timeline), probes_sha256=canonical_digest(probes),
                issued=len(timeline), admitted=sum(visits.values()), invalid=counts["invalid"], visits=visits,
                selected=sum(len(row["candidates"]) for row in probes), reads=reads)


def full_recovery(directory, mode, pin, expected, *, codec=None):
    from leo.storage.short_window import ShortWindowReader

    start = clock()
    if mode == "ordinary":
        reader = ShortWindowReader(directory)
        if reader.manifest_sha256 != pin:
            raise ValueError("Ordinary capture root changed before recovery")
        matched = sha256()
        for window in reader.windows():
            matched.update(memoryview(window.samples).cast("B"))
        digest = "sha256:" + matched.hexdigest()
    else:
        with seek.open_member(directory, pin, codec=codec) as reader:
            digest = reader.verify_all()
    if digest != expected:
        raise ValueError("Full restoration differs from the original physical CI16")
    return dict(timing=elapsed(start), decoded=digest)


def trial(root, *, orders=ORDERS, codecs=None, legacy_mode="split-level-1", member=ORIGINAL, short_binary=SHORT):
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    host = signed.check_machine()
    codecs = {} if codecs is None else codecs
    if root.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Expected a fresh tmpfs experiment")
    spec = json.loads(frozen.verified(frozen.PAYLOAD / "spec.json", frozen.SPEC_SHA))
    full = frozen.PAYLOAD / "receiver.so"
    pilot = frozen.RELEASE / "assets/lower.f32"
    hasher = frozen.PAYLOAD / "paired-sha256.so"
    for path, expected in ((full, spec["detector_sha256"]), (pilot, signed.PILOT_SHA["lower"]),
                           (short_binary, signed.SHORT_SHA), (hasher, spec["paired_sha256"]["sha256"])):
        frozen.verified(path, expected)
    ingress = frozen.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    reader, windows, source = verified_source(ingress, hasher, member)
    setup_started = clock()
    if codecs:
        source["raw_word_range"] = [min(int(row.samples.min()) for row in windows),
                                    max(int(row.samples.max()) for row in windows)]
    for module in ("leo.storage.fast_scan", "leo.scanner.fast_scan_analysis", "leo.contracts.fast_scan_native",
                   "tools.pipeline_eval.qualification.blind_compact_run"):
        import_module(module)
    asset = np.frombuffer(frozen.verified(pilot, signed.PILOT_SHA["lower"]), dtype="<f4")
    with ExitStack() as stack:
        for mode, binary in (("full", full), ("short_primary", short_binary)):
            engine = NativePath(binary, asset, mode)
            stack.callback(engine.close)
    shared_setup = elapsed(setup_started)
    root.mkdir(mode=0o700)
    comparisons, recovery, baseline = [], {}, None
    for order in orders:
        row = {}
        for mode in order:
            codec = codecs.get(mode)
            if codec is not None:
                codec.blocks.clear()
            with TemporaryDirectory(dir=root, prefix=f"{mode}-") as temp:
                begin = clock()
                directory, pin, written = capture(Path(temp), mode, reader.manifest, windows, codec=codec)
                first = analyze(directory, mode, pin, full, short_binary, pilot, ingress, hasher, codec=codec)
                both = elapsed(begin)
                if codec is not None:
                    written["block_widths"] = codec.counts()
                if (written["decoded_sha256"] != member.decoded or written["index_sha256"] != member.index
                        or first["issued"] != 64 or first["admitted"] + first["invalid"] != 64):
                    raise ValueError("Capture changed original bytes, metadata or eligibility")
                outcomes = {key: first[key] for key in MATCH}
                if baseline is None:
                    if member.prior_probes is not None and outcomes["probes_sha256"] != member.prior_probes:
                        raise ValueError("The ordinary reader must reproduce the independently sealed mixed probe digest")
                    baseline = outcomes
                if outcomes != baseline:
                    raise ValueError("Storage representation changed first mixed detector evidence")
                if mode not in recovery:
                    recovery[mode] = full_recovery(directory, mode, pin, member.decoded, codec=codec)
                row[mode] = dict(capture=written, first_analysis=first, capture_to_first=both)
        comparisons.append(row)

    with TemporaryDirectory(dir=root, prefix="legacy-") as temp:
        sidecar = Path(temp) / "converted"
        legacy_cost = Counter()
        codec = codecs.get(legacy_mode)
        if codec is not None:
            codec.blocks.clear()
        began = clock()
        with ingress(), paired_decoded_hashes(hasher):
            legacy_pin = seek.create(reader, 0, sidecar, costs=legacy_cost, codec=codec)
        legacy_conversion = elapsed(began) | dict(legacy_cost)
        legacy_analysis = None
        if codec is not None:
            legacy_analysis = analyze(sidecar, legacy_mode, legacy_pin, full, short_binary, pilot, ingress, hasher, codec=codec)
            if {key: legacy_analysis[key] for key in MATCH} != baseline:
                raise ValueError("Legacy conversion changed the ordered data or signed receiver evidence")
        legacy_recovery = full_recovery(sidecar, legacy_mode, legacy_pin, member.decoded, codec=codec)
        legacy_bytes = {path.name: path.stat().st_size for path in sidecar.iterdir()}
    active_modes = orders[0]
    signed.freeze(root / "result.json", dict(host=host, source=source, orders=orders,
                levels={mode: LEVELS.get(mode) for mode in active_modes},
                runs=comparisons, complete_recovery=recovery, legacy_conversion=legacy_conversion,
                legacy_first_analysis=legacy_analysis, legacy_recovery=legacy_recovery, legacy_bytes=legacy_bytes,
                accepted_science=baseline, common_setup=shared_setup,
                native_codecs={mode: codec.programme() for mode, codec in codecs.items()},
                decoder_version=zstd.ZSTD_VERSION,
                source_pins={"full": spec["detector_sha256"], "short": signed.SHORT_SHA,
                             "paired_sha256": spec["paired_sha256"]["sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    trial(parser.parse_args().root)
