"""Bounded two-lane GLRT handoff with the original recording commitments."""

import heapq
import json
from hashlib import sha256
from pathlib import Path

from ..variants.winner_stream import Writer
from . import capture_release
from . import recording_to_v5 as recording

MAX_LINE = 256 * 1024
MAX_SEGMENTS = 1024
EXCLUSION = ("visit", "reason", "iq_sha256", "sample_start", "sample_end")
RECIPE = "native-short-window-glrt/fractional-epoch"


def encoded(value):
    return recording.encoded(value).encode()


def digest(*parts):
    hash_ = sha256()
    for part in parts:
        hash_.update(part)
    return hash_


def array_add(hash_, previous, item):
    if previous:
        hash_.update(b",")
    hash_.update(item)


def lane_rows(path, worker, segments, lane_digest):
    """Validate original segment/worker footers with only one live visit per lane."""
    with path.open("rb") as stream:
        pending, current, last, terminal = 0, None, -1, False
        while line := stream.readline(MAX_LINE):
            if not line.endswith(b"\n") or terminal:
                raise ValueError("truncated or trailing detector record")
            lane_digest.update(line)
            row = json.loads(line)
            kind = row["kind"]
            if kind == "worker":
                if pending or row != {"kind": "worker", "worker": worker}:
                    raise ValueError("unfinished detector lane")
                terminal = True
                continue
            index = row["segment"]
            if not 0 <= index < MAX_SEGMENTS or index % 2 != worker:
                raise ValueError("detector segment differs from the lane schedule")
            if kind == "segment":
                if index in segments or not pending or current != index or row["count"] != pending:
                    raise ValueError("incomplete or duplicated detector segment")
                segments[index] = row
                pending, current = 0, None
            elif kind == "visit":
                if (
                    index in segments
                    or current not in (None, index)
                    or row["sequence"] != pending
                    or row["visit"] <= last
                ):
                    raise ValueError("unordered detector visit")
                pending, current, last = pending + 1, index, row["visit"]
                yield row
            else:
                raise ValueError("unknown detector lane record")
        if not terminal:
            raise ValueError("missing detector lane terminal receipt")


def merge(directory, segments, lane_digests):
    return heapq.merge(
        *(
            lane_rows(directory / f"replayed-{i}.jsonl", i, segments, h)
            for i, h in enumerate(lane_digests)
        ),
        key=lambda visit: visit["visit"],
    )


def inventory(case, segments, capture, library):
    rec = case["recording"]
    if set(segments) != set(range(len(rec["segments"]))):
        raise ValueError("detector lanes did not preserve every recording segment")
    authority, radios = [], set()
    for i, loc in enumerate(rec["segments"]):
        row = segments[i]
        if (
            row["manifest_digest"] != "sha256:" + loc["sha256"]
            or Path(row["path"]) != (recording.BULK / loc["path"]).parent
            or row["library_sha256"] != library
            or row.get("detector", "ordinary") != "ordinary"
        ):
            raise ValueError("detector segment, decoder or source binary authority differs")
        radios.add(row["radio_id"])
        authority.append(
            dict(
                scope=f"segment-{i:08d}",
                path=row["path"],
                manifest_digest=row["manifest_digest"],
                windows=row["count"],
            )
        )
    producer = capture_release.producer(case, capture)
    actual = capture_release.inventory_digest(authority, rec["window_count"])
    if actual != producer.input_manifest_sha256 or len(radios) != 1:
        raise ValueError("recording inventory or radio differs from the pinned decoder")
    return actual, radios.pop(), str(producer.root)


def virtual_native(directory, metadata, lane_pins):
    """Hash the old canonical public byte stream without materializing or writing it."""
    marker = b'"probes":null'
    template = encoded(dict(metadata, source=dict(metadata["source"], probes=None)))
    if template.count(marker) != 1:
        raise ValueError("legacy native probe field is ambiguous")
    top, tail = template.split(marker)
    legacy = digest(top, b'"probes":[')
    count, second = 0, (sha256(), sha256())
    for visit in merge(directory, {}, second):
        for probe in visit["probes"]:
            array_add(legacy, count, encoded(probe))
            count += 1
    if tuple(h.hexdigest() for h in second) != lane_pins:
        raise ValueError("detector messages changed during canonical digest reconstruction")
    legacy.update(b"]" + tail + b"\n")
    return legacy.hexdigest()


def assemble(directory, case, capture, library_sha, output):
    library = "sha256:" + library_sha
    expected_visits = case["recording"]["window_count"]
    if not 0 < expected_visits <= 50_000:
        raise ValueError("recording exceeds the bounded winner handoff")
    analysis = digest(
        b"[",
        encoded(RECIPE),
        b",",
        encoded(library),
        b",",
        encoded(capture["input_manifest_sha256"]),
        b",[",
    )
    support = digest(b"[")
    raw = digest(b"[", encoded(capture["input_manifest_sha256"]), b",[")
    segments, lane_hashes = {}, (sha256(), sha256())
    clocks, exclusions, anchors, mapping = [], [], [], set()
    generation = first = end = None
    probes = losing = candidates = positive = iq_bytes = 0
    writer = Writer(output)
    for index, row in enumerate(merge(directory, segments, lane_hashes)):
        if index == 0:
            generation, first = row["generation"], row["sample_start"]
            end = first
        if (
            row["visit"] != index
            or index >= expected_visits
            or row["generation"] != generation
            or row["delivery_clock"] is None
            or type(row["sample_start"]) is not int
            or type(row["sample_end"]) is not int
            or not end <= row["sample_start"] <= row["sample_end"]
        ):
            raise ValueError("a detector visit differs from the capture clock or counters")
        end = row["sample_end"]
        clocks.append(row["delivery_clock"])
        if row["clock_anchor"] is not None:
            anchors.append(row["clock_anchor"])
        iq_bytes += row["input_bytes"]
        mapping.add(row["rf_mapping_authority"])
        array_add(raw, index, encoded(row["iq_sha256"]))
        factors = row["probes"]
        if row["status"] == "invalid_capture" and not factors:
            exclusions.append({key: row[key] for key in EXCLUSION})
            continue
        if row["status"] != "processed" or [p["receiver_id"] for p in factors] != [0, 1]:
            raise ValueError("each valid detector visit requires its two original probes")
        for p in factors:
            if p["visit_index"] != index or p["valid_start_counter"] != row["sample_start"]:
                raise ValueError("detector probe differs from the visit authority")
            array_add(analysis, probes, encoded(p))
            array_add(support, probes, encoded({k: v for k, v in p.items() if k != "candidates"}))
            writer.probe(p)
            probes += 1
            losing += not p["candidates"]
            candidates += len(p["candidates"])
            positive += sum(c["passed_fractional_margin_gate"] for c in p["candidates"])
    if len(clocks) != expected_visits or len(anchors) != 1 or anchors[0]["sample_counter"] != first:
        raise ValueError("missing capture visits or unique initial UTC anchor")
    manifest, radio, decoder = inventory(case, segments, capture, library)
    analysis.update(b"]," + encoded(exclusions) + b"]")
    raw.update(b"]]")
    support.update(b"]")
    source = dict(
        session_id=case["session_id"],
        capture_mode="adaptive",
        sample_rate_hz=10_000_000,
        radio_id=radio,
        stream_generation=f"continuous-iio-{generation:016x}",
        input_manifest_sha256=manifest,
        analysis_manifest_sha256="sha256:" + analysis.hexdigest(),
        raw_recording_authority_digest="sha256:" + raw.hexdigest(),
        qualified=True,
        timing=None,
        probe_ms=20,
        capture_start_utc_ns=None,
        capture_end_utc_ns=None,
    )
    provenance = dict(
        run_id="replay-" + analysis.hexdigest()[:32],
        window_count=expected_visits,
        processed_windows=probes // 2,
        invalid_capture=len(exclusions),
        excluded_windows=exclusions,
        skipped_fast_score=0,
        rf_mapping_authorities=sorted(mapping),
        scope="fresh native fractional GLRT on the complete sealed recording",
        detector_sha256=library,
    )
    # Match the ordinary export's order so serialization also reproduces its private projection.
    metadata = dict(
        clock_anchor=anchors[0],
        delivery_clocks=clocks,
        last_sample_counter=end,
        provenance=provenance,
        schema_version=2,
        source=source,
    )
    lane_pins = tuple(h.hexdigest() for h in lane_hashes)
    native = virtual_native(directory, metadata, lane_pins)
    private, handoff_bytes = writer.finish(json.loads(encoded(metadata)), native)
    return dict(
        native_sha256="sha256:" + native,
        private_sha256=private,
        handoff_bytes=handoff_bytes,
        lane_sha256=lane_pins,
        decoder_root=decoder,
        input_manifest_sha256=manifest,
        analysis_manifest_sha256=source["analysis_manifest_sha256"],
        raw_authority=source["raw_recording_authority_digest"],
        clock_sha256=recording.digest([anchors[0], clocks, end]),
        excluded_sha256=recording.digest(exclusions),
        probes_sha256="sha256:" + support.hexdigest(),
        counts=dict(
            recording_windows=expected_visits,
            processed_windows=probes // 2,
            invalid_capture=len(exclusions),
            probe_rows=probes,
            empty_probe_rows=losing,
            candidate_rows=candidates,
            positive_candidates=positive,
            iq_bytes=iq_bytes,
            detector_cpu_s=sum(row["detector_cpu_s"] for row in segments.values()),
            window_delivery_span_s=(clocks[-1]["monotonic_ns"] - clocks[0]["monotonic_ns"]) / 1e9,
        ),
    )
