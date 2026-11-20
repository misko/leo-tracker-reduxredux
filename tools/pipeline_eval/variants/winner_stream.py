"""Private per-probe winner transport to the frozen phase-release Graph boundary."""

import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass

MAGIC = b"leo-winners/1\n"
PROBES = re.compile(rb'"probes"\s*:\s*\[')
BLOCK = 64 * 1024
MAX_METADATA = 8 * 1024 * 1024
MAX_PROBES = 100_000


def project(probe):
    """Drop candidate objects after counting the exact frozen frequency evidence."""
    candidates = probe["candidates"]
    distinct = []
    for candidate in sorted(candidates, key=lambda c: -c["fractional_margin"]):
        frequency = candidate["fractional_tracking_cfo_hz"]
        margin = candidate["fractional_margin"]
        epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
        if not all(map(math.isfinite, (frequency, margin, epoch))):
            raise ValueError("nonfinite candidate")
        if not any(abs(frequency - f) < 1.0 and abs(epoch - t) < 0.05 for f, t in distinct):
            distinct.append((frequency, epoch))
    winner = max(
        (c for c in candidates if c["passed_fractional_margin_gate"] is True),
        key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
        default=None,
    )
    values = (
        None
        if winner is None
        else (winner["fractional_tracking_cfo_hz"], winner["fractional_margin"])
    )
    return (
        probe["receiver_id"],
        probe["channel"],
        probe["actual_rf_hz"],
        probe["valid_start_counter"],
        probe.get("visit_index"),
        probe.get("probe_index"),
        len(candidates),
        len(distinct),
        values,
    )


def encode(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()


class Writer:
    """Pass one probe at a time and commit the stream with final capture clocks."""

    def __init__(self, stream):
        self.stream = stream
        self.hash = hashlib.sha256()
        self.count = 0
        self.bytes = 0
        self.closed = False
        self.write(MAGIC)

    def write(self, data):
        self.stream.write(data)
        self.hash.update(data)
        self.bytes += len(data)

    def probe(self, row):
        if self.closed or self.count >= MAX_PROBES:
            raise ValueError("private probe stream exceeded its open record budget")
        self.write(encode(project(row)) + b"\n")
        self.count += 1

    def finish(self, metadata, native_sha):
        if self.closed or not self.count or "probes" in metadata["source"]:
            raise ValueError("private stream must have a single footer and separate probes")
        footer = encode(dict(document=metadata, native_sha256=native_sha, probes=self.count))
        if len(footer) >= MAX_METADATA:
            raise ValueError("private capture metadata exceeds bounded read size")
        self.write(footer + b"\n")
        self.closed = True
        return self.hash.hexdigest(), self.bytes


def convert(stream, output, expected):
    """Convert one canonical stored native export, keeping at most one decoded probe."""
    source_hash = hashlib.sha256()

    def take():
        data = stream.read(BLOCK)
        source_hash.update(data)
        return data

    prefix = take()
    while (marker := PROBES.search(prefix)) is None:
        block = take()
        if not block or len(prefix) >= MAX_METADATA:
            raise ValueError("native export is missing the bounded probe array")
        prefix += block
    buffer = prefix[marker.end() :].decode("ascii")
    prefix = prefix[: marker.end() - 1]
    writer = Writer(output)
    decoder = json.JSONDecoder()
    index = 0
    while True:
        # Compact each block occasionally rather than copying the tail for every probe.
        if index > BLOCK or len(buffer) - index < 256:
            buffer, index = buffer[index:] + take().decode("ascii"), 0
        while index < len(buffer) and buffer[index].isspace():
            index += 1
        try:
            row, end = decoder.raw_decode(buffer, index)
        except json.JSONDecodeError:
            block = take()
            if not block or len(buffer) - index >= MAX_METADATA:
                raise ValueError("truncated or oversized native probe") from None
            buffer, index = buffer[index:] + block.decode("ascii"), 0
            continue
        writer.probe(row)
        index = end
        while True:
            while index < len(buffer) and buffer[index].isspace():
                index += 1
            if index < len(buffer):
                break
            block = take()
            if not block:
                raise ValueError("native probe array lacks a closing delimiter")
            buffer, index = block.decode("ascii"), 0
        delimiter = buffer[index]
        index += 1
        if delimiter == "]":
            break
        if delimiter != ",":
            raise ValueError("invalid native probe delimiter")
    tail = bytearray(buffer[index:].encode("ascii"))
    while block := take():
        tail.extend(block)
        if len(tail) >= MAX_METADATA:
            raise ValueError("native export tail exceeds its byte budget")
    origin = expected.removeprefix("sha256:")
    if source_hash.hexdigest() != origin:
        raise ValueError("native archive SHA-256 mismatch")
    sentinel = "winner-stream-probe-array"
    document = json.loads(prefix + encode(sentinel) + tail)
    if document["source"].pop("probes") != sentinel:
        raise ValueError("streamed probe array is outside the source object")
    return writer.finish(document, origin)


@dataclass
class WinnerInput:
    source: dict
    rows: list
    metadata: dict
    counts: dict

    def __getitem__(self, key):
        if key == "source":
            return self.source
        raise KeyError(key)


def observations(rows, document):
    source = document["source"]
    anchor = document["clock_anchor"]
    if anchor is None or not rows:
        raise ValueError("capture has no clock authority or probes")
    before, after = (anchor[k]["realtime_ns"] for k in ("before", "after"))
    if after < before or after - before > 2_000_000_000:
        raise ValueError("invalid UTC bracket")
    delivery = document["delivery_clocks"]
    offsets = [
        c["realtime_ns"] - c["monotonic_ns"] for c in (anchor["before"], anchor["after"], *delivery)
    ]
    if max(offsets) - min(offsets) > 2_000_000_000:
        raise ValueError("capture clock step")
    receivers = sorted({row[0] for row in rows})
    support = defaultdict(list)
    selected = []
    first, rate, ms = anchor["sample_counter"], source["sample_rate_hz"], source["probe_ms"]
    width = round(ms * 0.001 * rate)
    empty = duplicates = distinct = 0
    for receiver, channel, rf, start, _visit, _probe, count, kept, winner in rows:
        if channel not in range(1, 9) or start < first or not math.isfinite(rf) or rf <= 0:
            raise ValueError("invalid native receiver support")
        if not 0 <= kept <= count or bool(count) != bool(kept) or (winner is not None and not kept):
            raise ValueError("invalid native candidate counters")
        support[receiver].append((start, start + width))
        empty += not count
        duplicates += count - kept
        distinct += kept
        if winner is not None:
            cfo, margin = map(float, winner)
            if not (math.isfinite(cfo) and math.isfinite(margin)):
                raise ValueError("nonfinite winner")
            token = f"{source['session_id']}:{receiver}:{start}"
            selected.append(
                dict(
                    observation_id="sha256:" + hashlib.sha256(token.encode()).hexdigest(),
                    receiver=receivers.index(receiver) + 1,
                    native_receiver_id=receiver,
                    channel=int(channel),
                    time_s=float((start - first) / rate + ms * 0.0005),
                    measured_cfo_hz=cfo,
                    actual_rf_hz=float(rf),
                    fractional_margin=margin,
                )
            )
    for intervals in support.values():
        intervals.sort()
        if any(b[0] < a[1] for a, b in zip(intervals, intervals[1:], strict=False)):
            raise ValueError("overlapping/duplicate receiver evidence")
    if len({r["observation_id"] for r in selected}) != len(selected):
        raise ValueError("duplicate winning observation identity")
    selected.sort(key=lambda r: (r["receiver"], r["channel"], r["time_s"], r["observation_id"]))
    metadata = dict(
        anchor_utc_ns=(before + after) // 2,
        causal_cutoff_utc_ns=before,
        utc_half_width_s=(after - before) / 2e9,
        group_labels=[(r, band) for r in receivers for band in (0, 1)],
        receiver_factors=len(rows),
        empty_factors=empty,
        duplicate_candidates_removed=duplicates,
        distinct_candidates=distinct,
        duration_s=(document["last_sample_counter"] - first) / rate,
        mark_policy="softmax-margin-temperature-0.1; q=0.05+0.9*clip(margin/0.1)",
        calibrated=False,
        alias_period_hz=None,
        **document["provenance"],
    )
    excluded = document["provenance"].get("excluded_windows", ())
    counts = dict(
        probes=len(rows), winners=len(selected), deliveries=len(delivery), excluded=len(excluded)
    )
    return WinnerInput(source, selected, metadata, counts)


def read(path, expected, native_origin):
    digest = hashlib.sha256()
    rows = []
    with open(path, "rb") as handle:
        if handle.readline(len(MAGIC) + 1) != MAGIC:
            raise ValueError("unsupported private winner stream")
        digest.update(MAGIC)
        while line := handle.readline(MAX_METADATA):
            if not line.endswith(b"\n"):
                raise ValueError("truncated or oversized private winner record")
            digest.update(line)
            value = json.loads(line)
            if isinstance(value, dict):
                if handle.read(1):
                    raise ValueError("trailing data after private winner footer")
                break
            if not isinstance(value, list) or len(value) != 9 or len(rows) >= MAX_PROBES:
                raise ValueError("invalid private winner record")
            rows.append(value)
        else:
            raise ValueError("missing private winner footer")
    if digest.hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError("private winner stream SHA-256 mismatch")
    if value["native_sha256"] != native_origin.removeprefix("sha256:") or value["probes"] != len(
        rows
    ):
        raise ValueError("private header differs from the originating native archive")
    return observations(rows, value["document"])


def prepare(document, config):
    from leo.analysis.localization_v3.tracks import active_curvature, graph_tracks

    tracks, assigned = graph_tracks(document.rows, config)
    curved = [i for i, track in enumerate(tracks) if active_curvature(track)]
    return dict(
        observations=document.rows,
        metadata=document.metadata,
        tracks=tracks,
        graph_points=assigned,
        curved_indices=curved,
        status="tracks_prepared" if curved else "no_active_curvature",
    )
