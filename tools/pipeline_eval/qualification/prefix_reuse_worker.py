"""Read framed native GLRT increments and rebuild the ordinary position at each frontier."""

import json
import math
import sys
from collections import defaultdict
from functools import lru_cache
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native

HORIZONS = (120, 180, 240, 300)
RATE = 10_000_000
PROBE = 200_000


class NativeIncrements:
    def __init__(self, setup):
        self.request = setup["request"]
        anchor = setup["anchor"]
        self.first = anchor["sample_counter"]
        before, after = (anchor[k]["realtime_ns"] for k in ("before", "after"))
        if (
            self.request["mode"] != "native"
            or self.request["cutoff"] != before
            or self.request["catalog_timestamp"] > before
            or not 0 <= after - before <= 2_000_000_000
        ):
            raise ValueError("invalid fixed causal acquisition authority")
        self.clock = dict(anchor_utc_ns=(before + after) // 2, cutoff_utc_ns=before)
        self.frontier = self.first
        self.index = 0
        self.receiver_end = {}
        self.lanes = defaultdict(list)
        self.probes = self.winners = self.bytes = 0

    def add(self, event, byte_count):
        cutoff, last, probes = (event[k] for k in ("checkpoint", "last_sample_counter", "probes"))
        end = self.first + RATE * cutoff
        if (
            self.index >= len(HORIZONS)
            or cutoff != HORIZONS[self.index]
            or not self.frontier <= last <= end
            or event["previous_probes"] != self.probes
            or event["expected_probes"] != self.probes + len(probes)
            or event["expected_probes"] > self.request["probe_limit"]
            or self.bytes + byte_count > native.ARCHIVE_LIMIT
        ):
            raise ValueError("noncausal, repeated or excessive increment")
        receiver_end, additions = self.receiver_end.copy(), defaultdict(list)
        winners = 0
        for row in probes:
            rx, channel = row["receiver_id"], row["channel"]
            rf, start = row["actual_rf_hz"], row["valid_start_counter"]
            if (
                rx not in (0, 1)
                or channel not in range(1, 9)
                or not 1e9 < rf < 100e9
                or not self.frontier < start + PROBE <= last
                or start < receiver_end.get(rx, self.first)
                or len(row["candidates"]) > 8
            ):
                raise ValueError("invalid or overlapping native increment")
            receiver_end[rx] = start + PROBE
            accepted = [c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True]
            if not accepted:
                continue
            winner = max(accepted, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
            frequency = winner["fractional_tracking_cfo_hz"]
            if not math.isfinite(frequency) or not math.isfinite(winner["fractional_margin"]):
                raise ValueError("nonfinite winning candidate")
            at = (start - self.first) / RATE + 0.01
            additions[rf, rx + 1, channel].append((at, frequency))
            winners += 1
            if len(self.lanes.keys() | additions.keys()) > 16:
                raise ValueError("native archive exceeds the dual-receiver lane budget")
        if set(receiver_end) != {0, 1}:
            raise ValueError("native capture needs both original receivers")
        self.receiver_end = receiver_end
        for key, points in additions.items():
            self.lanes[key].extend(points)
        self.winners += winners
        self.probes += len(probes)
        self.bytes += byte_count
        self.frontier = last
        self.index += 1

    def peak_lanes(self, _record, probe_limit, cutoff):
        if probe_limit < self.probes or cutoff != self.clock["cutoff_utc_ns"]:
            raise ValueError("native consumer changed its authenticated input authority")
        return (
            dict(self.clock, duration_s=(self.frontier - self.first) / RATE),
            self.lanes,
            dict(native_bytes=self.bytes, probes=self.probes, winning_peaks=self.winners),
        )


def command(input_stream, output):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.qualification import online_prefix_worker
    from tools.pipeline_eval.qualification.prefix_reuse_cache import EphemerisReuse
    from tools.pipeline_eval.variants import robust_orbit_fit

    setup = input_stream.readline(native.BLOCK_BYTES + 1)
    if len(setup) > native.BLOCK_BYTES or not setup.endswith(b"\n"):
        raise ValueError("missing bounded initialization frame")
    series = NativeIncrements(json.loads(setup))
    grid = robust_orbit_fit.grid
    cache = EphemerisReuse(grid)
    parser = lru_cache(maxsize=1)(grid.parse_element_sets)
    read = native._load

    @lru_cache(maxsize=2)
    def bound_file(path, digest, limit):
        return read(dict(path=path, sha256=digest), limit)

    def immutable(record, limit):
        return bound_file(record["path"], record["sha256"], limit)

    while True:
        started = native._now()
        raw = input_stream.readline(native.ARCHIVE_LIMIT + 1)
        if not raw:
            break
        if len(raw) > native.ARCHIVE_LIMIT or not raw.endswith(b"\n"):
            raise ValueError("partial or excessive increment frame")
        event = json.loads(raw)
        series.add(event, len(raw))
        del event, raw
        ingestion = native._elapsed(started)
        previous = cache.sums()
        with (
            patch.object(grid, "_valid_states", cache),
            patch.object(grid, "parse_element_sets", parser),
            patch.object(native, "peak_lanes", series.peak_lanes),
            patch.object(native, "_load", immutable),
        ):
            result = online_prefix_worker.worker(series.request)
        after = cache.sums()
        result.update(
            worker=native._elapsed(started),
            cumulative_input_bytes=series.bytes,
            last_sample_counter=series.frontier,
            ephemeris_cache=dict(
                {k: after[k] - previous[k] for k in after if k != "retained_bytes"},
                retained_bytes=after["retained_bytes"],
            ),
        )
        result["stages"]["increment_decode_and_peaks"] = ingestion
        json.dump(result, output, allow_nan=False, sort_keys=True)
        output.write("\n")
        output.flush()


if __name__ == "__main__":
    command(sys.stdin.buffer, sys.stdout)
