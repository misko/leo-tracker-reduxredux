"""Write one conventional resident archive with independently pinned seek tables."""

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from inspect import getfile, unwrap
from pathlib import Path
from runpy import run_path
from unittest.mock import patch
from uuid import uuid4

from .owned_capture_0016 import (
    LOGICAL,
    MANIFESTS,
    STAGE,
    STAGE_PIN,
    WINDOWS,
    checked,
    logical,
)

QUALIFICATION = Path("/dev/shm/leo-v3-frame-visit-0016-result02.json")
QUALIFICATION_PIN = "0f20009514737da994f1f819bb54080dd38a360233259e0cddacf7edf97c382c"
QUALIFIED_RUNNER = "65caa9376722f34ca6216bbba260e9893f607c513bbdecb80a4b6c9e33f84644"
READER_PIN = "0884ab7ca630d59dd041e50e0ef89cd847ca842c11097f8bde06b869645eafa2"
SCHEMA = "private-algo08-visit-frame-custody-v1"
LIMIT = 1_600_000_000


@dataclass(frozen=True)
class RecordingInput:
    case: str
    custody: Path
    custody_sha256: str
    recording: Path | None
    manifests: tuple
    windows: int
    limit: int
    repeat_qualified_member: bool = False
    extents: tuple = ()


def recording_input(path=None, pin=None):
    if path is None and pin is None:
        return RecordingInput("DS30-0016", STAGE / "staging.json", STAGE_PIN, None,
                              MANIFESTS, WINDOWS, LIMIT, repeat_qualified_member=True)
    if path is None or pin is None:
        raise ValueError("Supply both the recording configuration and its frozen digest")
    doc = json.loads(checked(path, pin))
    return RecordingInput(
        case=doc["case"], custody=Path(doc["custody"]), custody_sha256=doc["custody_sha256"],
        recording=Path(doc["recording"]), manifests=tuple(map(tuple, doc["manifests"])),
        windows=doc["windows"], limit=doc["limit"],
        repeat_qualified_member=doc["repeat_qualified_member"],
        extents=tuple(map(tuple, doc["extents"])),
    )


def resident_path(path, device=None):
    if path != path.resolve(strict=True) or not path.is_relative_to("/dev/shm"):
        raise ValueError(f"Only literal tmpfs staging paths are authorized: {path}")
    if device is not None and path.stat().st_dev != device:
        raise ValueError(f"Staged member crosses the tmpfs boundary: {path}")
    return path


def verify_qualification():
    prior = json.loads(checked(QUALIFICATION, QUALIFICATION_PIN))
    source = prior["source"]
    compressed = prior["captures"]["ordinary"]["chunk"]["compressed_sha256"]
    new = prior["captures"]["frames"]["chunk"]
    suffix = prior["corrupt_unused_suffix"]
    sidecar = prior["corrupt_sidecar"]
    if (prior["runner_sha256"] != QUALIFIED_RUNNER or prior["reader_sha256"] != READER_PIN
            or source["case"] != "DS30-0016" or source["compressed"] != compressed
            or new["compressed_sha256"] == compressed or new["window_count"] != 64
            or prior["captures"]["frames"]["sidecar_sha256"] is None
            or suffix["issued_visits"] or type(suffix["scheduled_short_sequence"]) is not int
            or "short-window member changed" not in suffix["rejected"]
            or sidecar["issued_visits"] or "frozen pin" not in sidecar["rejected"]):
        raise ValueError("The signed matched physical member corruption gate did not pass")
    return new


def write_table(path, manifest_pin, chunk, records, schema):
    from leo.contracts.digests import canonical_json_bytes, sha256_digest
    from leo.storage.writer import _fsync_directory

    if (len(records) != chunk.window_count
            or any(i != row["sequence"] for i, row in enumerate(records))):
        raise ValueError("Payload writer did not preserve ordered rows for the member")
    records = [dict(row, sequence=chunk.first_sequence + i) for i, row in enumerate(records)]
    doc = dict(schema=schema, manifest_sha256=manifest_pin, index_sha256=chunk.index_sha256,
               compressed_sha256=chunk.compressed_sha256, records=records)
    content = canonical_json_bytes(doc)
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)
    return sha256_digest(content)


def current_tree_bytes(root):
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def stage_names(reader):
    manifest = reader.path / "manifest.json"
    return [(reader.path, manifest.name, manifest.stat().st_size)] + [
        (reader.path, member, length) for chunk in reader.manifest.chunks for member, length in (
            (chunk.index_relative_path, chunk.index_bytes),
            (chunk.payload_relative_path, chunk.compressed_bytes),
        )
    ]


def original_windows(source, chunk, ingress, paired, hasher):
    from leo.storage.short_window import ShortWindowReader

    expected = {
        chunk.index_relative_path: (chunk.index_bytes, chunk.index_sha256),
        chunk.payload_relative_path: (chunk.compressed_bytes, chunk.compressed_sha256),
    }
    opened = set()
    ordinary = ShortWindowReader._member

    def scoped(reader, name, size, pin):
        if reader.path != source.path or expected.get(name) != (size, pin) or name in opened:
            raise ValueError("Original hydration crossed the pinned staged member")
        opened.add(name)
        return ordinary(reader, name, size, pin)

    with (patch.object(ShortWindowReader, "_member", scoped), ingress(), paired(hasher)):
        rows = tuple(source.windows(start_sequence=chunk.first_sequence,
                                    stop_sequence=chunk.first_sequence + chunk.window_count))
    if len(rows) != chunk.window_count or opened != set(expected):
        raise ValueError("Hydration did not exhaust the exact original member")
    if any(row.samples.flags.writeable or row.samples.nbytes != row.index.payload_bytes
           for row in rows):
        raise ValueError("Owned source must consist of immutable verified windows")
    return rows


def lifecycle(manifest):
    return {name: getattr(manifest, name) for name in (
        "created_utc_ns", "finalized_utc_ns", "status", "stop_reason", "failure",
    )}


def preserve_clock(actual, original):
    stable = ("configuration", "radio", "sample_rate_hz", "receiver_ids", "status", "stop_reason",
              "failure", "window_count", "schema_version", "window_ms", "sample_format",
              "sample_layout")
    if any(getattr(actual, key) != getattr(original, key) for key in stable):
        raise ValueError("New segment changed original capture metadata or lifecycle")


def writer_scope(source, path, ingress, paired, hasher, output_root, shared, *, limit=LIMIT):
    from leo.storage import short_window

    from .frame_visit_0016 import SCHEMA as TABLE_SCHEMA
    from .frame_visit_0016 import VisitFrames
    from .seekable_eight_raw import clocks, elapsed

    header = source.manifest
    if [chunk.window_count for chunk in header.chunks[:-1]] != [64] * (len(header.chunks) - 1):
        raise ValueError("The staged archive has a nonstandard member boundary")
    start = clocks()
    writer = short_window.ShortWindowWriter(
        path.parent, path.name, configuration=header.configuration, radio=header.radio,
        receiver_ids=header.receiver_ids, chunk_windows=64, compression_level=1,
        schema_version=header.schema_version,
    )
    writer_costs = Counter(elapsed(start))
    input_costs, records = [], []
    hashes, extents = [], Counter()

    def emit(filename, *, level):
        table = []
        records.append(table)
        return VisitFrames(filename, level, table)

    try:
        with patch.object(short_window, "_CompressedFileWriter", emit):
            for chunk in header.chunks:
                start = clocks()
                owned = original_windows(source, chunk, ingress, paired, hasher)
                hydrate = elapsed(start)
                if hydrate["input_blocks"] or hydrate["major_faults"]:
                    raise ValueError("Resident waveform hydration charged external reads")
                # Allow the new payload to grow to the member's decoded size plus codec headroom.
                projected = (current_tree_bytes(output_root) + 2 * chunk.uncompressed_bytes
                             + 2_000_000)
                if projected > limit:
                    raise ValueError("Owned and encoded extents exceed the retained byte budget")
                shared["max_accounted_bytes"] = max(shared["max_accounted_bytes"], projected)
                start = clocks()
                for window in owned:
                    row = window.index
                    writer.append(sequence=row.sequence, target_id=row.target_id,
                                  samples=window.samples, acquisition=row.acquisition,
                                  powers=row.powers)
                writer_costs.update(elapsed(start))
                hashes.extend((row.index.iq_sha256, row.index.acquisition["global_visit"])
                              for row in owned)
                extents.update(row.index.payload_bytes for row in owned)
                input_costs.append(dict(chunk=chunk.chunk_index, clock=hydrate))
                del owned, window
            start = clocks()
            writer.finish(stop_reason=header.stop_reason, failure=header.failure)
            writer_costs.update(elapsed(start))
    except BaseException:
        writer.abort()
        raise

    start = clocks()
    written = short_window.ShortWindowReader(path)
    preserve_clock(written.manifest, header)
    current = [chunk.model_dump(mode="json") for chunk in written.manifest.chunks]
    original = [chunk.model_dump(mode="json") for chunk in header.chunks]
    if logical(current) != logical(original) or written.manifest_sha256 == source.manifest_sha256:
        raise ValueError("New archive changed logical hashes or reused an original manifest")
    members = []
    for chunk, index, old in zip(written.manifest.chunks, records, original, strict=True):
        name = f"visit-frames-{chunk.chunk_index:06d}.json"
        pin = write_table(path / name, written.manifest_sha256, chunk, index, TABLE_SCHEMA)
        fields = (*LOGICAL, "compressed_bytes", "compressed_sha256")
        data = {key: getattr(chunk, key) for key in fields}
        members.append(dict(data, side_name=name, side_sha256=pin,
                            original_compressed_sha256=old["compressed_sha256"],
                            original_compressed_bytes=old["compressed_bytes"]))
    seek_clock = elapsed(start)
    report = dict(directory=path.name, manifest_sha256=written.manifest_sha256,
                  original_manifest_sha256=source.manifest_sha256, window_count=len(hashes),
                  lifecycle=lifecycle(written.manifest), original_lifecycle=lifecycle(header),
                  members=members)
    return report, dict(hydrate=input_costs, writer=dict(writer_costs), seek=seek_clock,
                        payload_extent_counts=sorted(extents.items())), hashes


def readback(recording, reports, expected, data_authority):
    from leo.contracts.digests import canonical_digest, sha256_digest
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader

    from .frame_visit_0016 import PREFIX_BYTES, SelectiveMember
    from .seekable_eight_raw import clocks, elapsed

    start = clocks()
    store = FastScanStore(recording)
    session, inventory_pin, inventory = store.inventory(recording, verify_windows=False)
    hashes, prefixes, verified_segments = [], {}, []
    for entry, segment in zip(inventory["segments"], reports, strict=True):
        if (Path(entry["path"]).name, entry["manifest_digest"]) != (
            segment["directory"], segment["manifest_sha256"],
        ):
            raise ValueError("Released inventory did not bind the fresh conventional segment")
        stream, segment_hashes = FastSegmentSource(entry), []
        for window in stream.windows():
            segment_hashes.append((window.iq_sha256, window.acquisition["global_visit"]))
            raw = memoryview(window.samples.reshape(-1)).cast("B")
            prefixes[segment["directory"], window.sequence] = sha256_digest(raw[:PREFIX_BYTES])
        hashes.extend(segment_hashes)
        verified_segments.append(dict(directory=segment["directory"],
                                      window_count=len(segment_hashes),
                                      window_hashes_sha256=canonical_digest(segment_hashes)))
    if hashes != expected:
        raise ValueError("Released readback changed the authenticated order or window bytes")
    whole = elapsed(start)
    raw = canonical_digest([inventory_pin, [digest for digest, _ in hashes]])
    if inventory_pin == data_authority["inventory"] or raw == data_authority["raw_authority"]:
        raise ValueError("Fresh capture did not get new ordinary source identities")
    selective_times = []
    for segment in reports:
        reader = ShortWindowReader(recording / segment["directory"])
        for chunk, member in zip(reader.manifest.chunks, segment["members"], strict=True):
            start = clocks()
            scoped = SelectiveMember(reader, member["side_sha256"], chunk=chunk,
                                     side_name=member["side_name"])
            for row in scoped.rows:
                prefix = scoped.read(row, full=False)
                if (prefix.nbytes != min(row.payload_bytes, PREFIX_BYTES)
                        or sha256_digest(memoryview(prefix.reshape(-1)).cast("B"))
                        != prefixes[segment["directory"], row.sequence]):
                    raise ValueError("Verified seek reader did not reproduce the committed prefix")
            selective_times.append(dict(segment=segment["directory"], member=chunk.chunk_index,
                                        clock=elapsed(start), counts=dict(scoped.counts)))
            del scoped, prefix
    return dict(session_id=session, inventory_sha256=inventory_pin, raw_authority=raw,
                window_count=len(hashes), window_hashes_sha256=canonical_digest(hashes),
                stock_clock=whole, seek_checks=selective_times, verified_segments=verified_segments,
                verified_index_sha256=sha256_digest(json.dumps([
                    member["index_sha256"] for report in reports for member in report["members"]
                ]).encode()))


def run(output, source_config=None, source_config_pin=None):
    from leo.contracts.digests import canonical_digest
    from leo.storage.short_window import ShortWindowReader
    from leo.storage.writer import _fsync_directory
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    from .aperture_trial import machine
    from .direct_packed_capture import close_file
    from .empty_bootstrap import BASELINE, BASELINE_PIN, PAYLOAD, RELEASE
    from .north_direct_multichunk import checked_lease, require_tmpfs
    from .seekable_eight_raw import clocks, elapsed
    from .sparse_cold_input import CACHE_LIBRARY, CACHE_SHA, frozen_function

    source_input = recording_input(source_config, source_config_pin)
    worker_started = clocks()
    checked_lease()
    checked(BASELINE, BASELINE_PIN)
    spec = run_path(str(BASELINE))["checked_spec"](PAYLOAD)
    ingress = frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    paired_pin = spec["sources"]["tools/pipeline_eval/variants/experimental/paired_sha256.py"]
    checked(Path(getfile(unwrap(paired_decoded_hashes))), paired_pin)
    host = machine()
    if (host["cpu"] != [2] or host["nice"] != 15 or host["ionice"] != "best-effort: prio 7"
            or set(host["threads"].values()) != {"1"} or os.environ.get("OMP_THREAD_LIMIT") != "1"):
        raise ValueError("Expected the ordinary low-priority one-core slot")
    first_member = verify_qualification()
    if output.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs experiment root")
    installed_reader = Path(getfile(ShortWindowReader))
    if not installed_reader.is_relative_to(RELEASE / "src"):
        raise ValueError("Readback must use the unmodified installed ShortWindowReader")
    checked(installed_reader, READER_PIN)
    residency_clock = clocks()
    custody_path = resident_path(source_input.custody)
    require_tmpfs(custody_path)
    authority = json.loads(checked(custody_path, source_input.custody_sha256))
    source = resident_path(
        source_input.recording or custody_path.parent / Path(authority["recording"]).name,
    )
    require_tmpfs(source)
    if authority["case"] != source_input.case:
        raise ValueError("Expected the complete staged weak physical source")
    checked(CACHE_LIBRARY, CACHE_SHA)
    repo = Path(__file__).resolve().parents[3]
    cache = run_path(str(repo / "tools/pipeline_eval/qualification/cache_residency.py"))
    query = cache["load_query"](CACHE_LIBRARY)
    expected_names = [source / f"{source.name}-segment-{i:08d}" / "manifest.json"
                      for i in range(len(source_input.manifests))]
    if sorted(source.glob("*/manifest.json")) != expected_names:
        raise ValueError("Unexpected staged segment coverage")
    admitted = []
    device = source.stat().st_dev
    for path, (pin, count, members) in zip(expected_names, source_input.manifests, strict=True):
        resident_path(path, device)
        reader = ShortWindowReader(path.parent)
        if (reader.manifest_sha256, reader.manifest.window_count, len(reader.manifest.chunks)) != (
            "sha256:" + pin, count, members,
        ):
            raise ValueError("Staged manifest differs from the exact qualified case")
        names = stage_names(reader)
        for folder, name, _ in names:
            resident_path(folder / name, device)
        state = cache["cache_snapshot"](names, os.sysconf("SC_PAGE_SIZE"), query)
        if (state["observed_members"] != len(names) or state["unavailable"]
                or state["cached_pages"] != state["observed_file_pages"]):
            raise ValueError("Only fully resident staged input members are authorized")
        admitted.append((reader, state))
    source_check = elapsed(residency_clock)
    if source_check["input_blocks"] or source_check["major_faults"]:
        raise ValueError("Staged source admission charged external reads")
    output.mkdir(mode=0o700)
    uid = uuid4().hex
    recording = output / f"recording-{uid}"
    recording.mkdir(mode=0o700)
    hasher = Path(spec["paired_sha256"]["library"])
    shared = dict(max_accounted_bytes=0)
    segments, clocks_by_segment, ordered = [], [], []
    extents = Counter()
    for i, (reader, state) in enumerate(admitted):
        path = recording / f"segment-{i:08d}-{uid}"
        row, times, hashes = writer_scope(reader, path, ingress,
                                          paired_decoded_hashes, hasher, output, shared,
                                          limit=source_input.limit)
        segments.append(row)
        clocks_by_segment.append(dict(segment=i, cache=state, **times))
        extents.update(dict(times["payload_extent_counts"]))
        ordered.extend(hashes)
    if ([visit for _, visit in ordered] != list(range(source_input.windows))
            or canonical_digest([authority["inventory"], [digest for digest, _ in ordered]])
            != authority["raw_authority"]):
        raise ValueError("The ordered samples differ from the original recording authority")
    if source_input.extents and extents != dict(source_input.extents):
        raise ValueError("The authenticated visit extents differ from the frozen recording")
    first = segments[0]["members"][0]
    fields = ("compressed_sha256", "compressed_bytes", *LOGICAL)
    if (source_input.repeat_qualified_member
            and any(first[key] != first_member[key] for key in fields)):
        raise ValueError("First emitted member differs from the signed physical corruption witness")
    verified = readback(recording, segments, ordered, authority)
    expected_members = sum(row[2] for row in source_input.manifests)
    if sum(len(row["members"]) for row in segments) != expected_members:
        raise ValueError("The complete output missed an original member")
    start = clocks()
    custody = dict(schema=SCHEMA, recording=str(recording), session_id=verified["session_id"],
                   inventory_sha256=verified["inventory_sha256"],
                   raw_authority=verified["raw_authority"],
                   window_count=verified["window_count"], segments=segments)
    custody_pin = close_file(output / "capture-authority.json", custody)
    _fsync_directory(recording)
    _fsync_directory(output)
    seal_cost = elapsed(start)
    archive_bytes = current_tree_bytes(recording)
    if archive_bytes > source_input.limit:
        raise ValueError("Archive exceeded its agreed retained byte limit")
    receipt = dict(case=source_input.case, source_custody_sha256=source_input.custody_sha256,
                   source_config_sha256=source_config_pin, source_check_clock=source_check,
                   new_recording=str(recording), payload_extent_counts=sorted(extents.items()),
                   qualification_sha256=QUALIFICATION_PIN, machine=host,
                   capture_authority_sha256=custody_pin, clocks=clocks_by_segment,
                   captured_bytes=archive_bytes, custody_write_clock=seal_cost, readback=verified,
                   original_inventory_sha256=authority["inventory"],
                   original_raw_authority=authority["raw_authority"], **shared,
                   worker_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                   worker_clock_through_archive=elapsed(worker_started))
    close_file(output / "receipt.json", receipt)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--input", type=Path)
    cli.add_argument("--input-sha256")
    params = cli.parse_args()
    run(params.output, params.input, params.input_sha256)
