"""Retain unchanged short factors supported by continuation or an independent stereo measurement."""

from collections import defaultdict, deque
from hashlib import sha256
from itertools import groupby
from math import remainder
from pathlib import Path
from statistics import median

from causal_short_receiver import FILTER_SHA
from north_factor_swap import rebound


RATE = 10_000_000
FRAME_HZ = 750
MAX_TIMING_SAMPLES = 2.
MAX_CFO_HZ = 1000.
WITNESSES = 3
WINDOWS = 12
HORIZON = 8 * RATE
STEREO_KEYS = ("channel", "actual_rf_hz", "edge")


def epoch(factor):
    return factor["integer_epoch_sample"] + factor["fractional_epoch_offset_samples"]


def timing_delta(left, right, first, second):
    ticks = right["valid_start_counter"] - left["valid_start_counter"]
    aligned = ticks * FRAME_HZ % RATE / FRAME_HZ
    return remainder(aligned + epoch(second) - epoch(first), RATE / FRAME_HZ)


def witness_offset(history, current):
    accepted = [value for time, value in history if 0 < current - time <= HORIZON and value is not None]
    if len(accepted) < WITNESSES:
        return None
    close = accepted[-WITNESSES:]
    offset = median(close)
    return offset if all(abs(value - offset) <= MAX_CFO_HZ for value in close) else None


def select(probes, history):
    """Retain independently reported factors and return measurement-only audit rows."""
    output, evidence = [], []
    by_stream = defaultdict(lambda: deque(maxlen=WINDOWS))
    previous = -1
    for visit, same_visit in groupby(probes, key=lambda probe: probe["visit_index"]):
        pair = list(same_visit)
        if visit <= previous or len(pair) != 2 or {p["receiver_id"] for p in pair} != {0, 1}:
            raise ValueError("Expected chronological independent RX0 and RX1 opportunities")
        previous = visit
        left, right = sorted(pair, key=lambda p: p["receiver_id"])
        stream = tuple(left[key] for key in STEREO_KEYS)
        if tuple(right[key] for key in STEREO_KEYS) != stream:
            raise ValueError("Stereo confirmation requires the same RF, channel and pilot edge")
        lane_factors = [row["candidates"] for row in (left, right)]
        if any(len(factors) > 1 or any(not f["passed_fractional_margin_gate"] for f in factors) for factors in lane_factors):
            raise ValueError("Expected at most one independently verified maximum-margin factor per lane")
        histories = by_stream[stream]
        now = max(p["valid_start_counter"] for p in pair)
        center = witness_offset(histories, now)
        mode, delta, cfo, witness = None, None, None, None
        if all(lane_factors):
            first, second = (factors[0] for factors in lane_factors)
            delta = timing_delta(left, right, first, second)
            cfo = second["fractional_tracking_cfo_hz"] - first["fractional_tracking_cfo_hz"]
            if abs(delta) <= MAX_TIMING_SAMPLES:
                witness = cfo
                if abs(cfo - (0. if center is None else center)) <= MAX_CFO_HZ:
                    mode = "direct" if center is None else "prior_offset"
        histories.append((now, witness))
        row_evidence = []
        for row in pair:
            _, continued, votes = history.select(row)
            keep = continued is not None or mode is not None
            output.append(dict(row, candidates=row["candidates"] if keep else []))
            row_evidence.append(dict(receiver=row["receiver_id"], counter=row["valid_start_counter"],
                                     had_factor=bool(row["candidates"]), continued=continued is not None,
                                     rescued=continued is None and mode is not None, votes=votes))
        evidence.append(dict(visit=visit, channel=stream[0], rf_hz=stream[1], edge=stream[2],
                             timing_delta_samples=delta, cfo_delta_hz=cfo, stereo_mode=mode,
                             timing_match=witness is not None, prior_offset_hz=center, lanes=row_evidence))
    return output, evidence


def filtered(native):
    from tools.pipeline_eval.variants import carrier_continuation

    source = native["source"]
    if not source["qualified"] or source["sample_rate_hz"] != RATE or source["probe_ms"] != 20:
        raise ValueError("Expected a qualified signed 10 MS/s stereo packet")
    if sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest() != FILTER_SHA:
        raise ValueError("The released carrier continuation changed")
    rows, evidence = select(source["probes"], carrier_continuation.Continuation())
    identity = ["history or independent signed stereo v1", source["sample_rate_hz"],
                native["provenance"]["detector_sha256"], "sha256:" + FILTER_SHA,
                "sha256:" + sha256(Path(__file__).read_bytes()).hexdigest()]
    return rebound(native, rows, identity), evidence, identity
