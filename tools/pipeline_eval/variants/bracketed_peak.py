"""Reconsider a measured weak peak between two original pilot detections."""

from collections import Counter, deque
from dataclasses import dataclass, field
from math import isfinite

from .coherent_peak_filter import (
    FOLD_HZ,
    FRAME_RATE_HZ,
    MAX_CFO_RATE_HZ_S,
    MAX_GAP_S,
    Peak,
    wrapped,
)
from .track_epoch import counter_phase

GATE = "passed_fractional_margin_gate"
NUMERIC_FIELDS = (
    "integer_epoch_sample",
    "fractional_epoch_offset_samples",
    "fractional_tracking_cfo_hz",
    "fractional_margin",
    "fractional_exact_score",
    "fractional_control_score",
)
MAX_LANES = 64
MAX_PENDING = 128
MAX_DRIFT = 50e-6
EPOCH_TOLERANCE = 2.0
CFO_TOLERANCE = 1000.0


@dataclass
class Lane:
    anchor: Peak | None = None
    pending: deque = field(default_factory=deque)
    counter: int = -1


def change(left, right, rate):
    elapsed = right.counter - left.counter
    if left.visit >= right.visit or not 0 < elapsed <= rate * MAX_GAP_S:
        return None
    phase = wrapped(counter_phase(elapsed, rate) + right.epoch - left.epoch, rate / FRAME_RATE_HZ)
    cfo = wrapped(right.cfo_hz - left.cfo_hz, FOLD_HZ)
    if abs(phase) > elapsed * MAX_DRIFT or abs(cfo) > MAX_CFO_RATE_HZ_S * elapsed / rate:
        return None
    return phase, cfo


def close_peak(epoch, cfo, other_epoch, other_cfo, period):
    return (
        abs(wrapped(epoch - other_epoch, period)) <= EPOCH_TOLERANCE
        and abs(wrapped(cfo - other_cfo, FOLD_HZ)) <= CFO_TOLERANCE
    )


def select_middle(probe, counter, left, right, motion, rate, sham):
    if not left.visit < probe["visit_index"] < right.visit:
        return None
    delta = counter - left.counter
    fraction = delta / (right.counter - left.counter)
    period = rate / FRAME_RATE_HZ
    epoch = left.epoch - counter_phase(delta, rate) + fraction * motion[0]
    if sham:
        epoch += period / 2
    cfo = left.cfo_hz + fraction * motion[1]
    same = []
    for i, candidate in enumerate(probe["candidates"]):
        values = [candidate.get(key) for key in NUMERIC_FIELDS]
        if not all(isinstance(value, (int, float)) and isfinite(value) for value in values):
            continue
        if (
            candidate.get(GATE) is not False
            or type(candidate.get("candidate_rank")) is not int
            or candidate["fractional_margin"] <= 0
            or candidate["fractional_exact_score"] <= candidate["fractional_control_score"]
        ):
            continue
        measured = Peak.from_candidate(probe, counter, candidate)
        if not close_peak(epoch, cfo, measured.epoch, measured.cfo_hz, period):
            continue
        if any(
            not close_peak(old.epoch, old.cfo_hz, measured.epoch, measured.cfo_hz, period)
            for _, old in same
        ):
            return None
        same.append((i, measured))
    return max(
        (i for i, _ in same),
        key=lambda i: (
            probe["candidates"][i]["fractional_margin"],
            -probe["candidates"][i]["candidate_rank"],
        ),
        default=None,
    )


def select(probes, rate, *, sham=False):
    if type(rate) is not int or rate <= 0:
        raise ValueError("a positive integer sample rate is required")
    lanes, edits, counts = {}, [], Counter()
    for i, probe in enumerate(probes):
        key = tuple(probe[k] for k in ("receiver_id", "channel", "actual_rf_hz", "edge"))
        if key not in lanes and len(lanes) >= MAX_LANES:
            raise ValueError("physical lane count exceeds the bounded receiver")
        if key not in lanes:
            lanes[key] = Lane()
        lane = lanes[key]
        counter = probe["valid_start_counter"] + round(probe["probe_start_ms"] * rate / 1000)
        if type(counter) is not int or counter <= lane.counter:
            raise ValueError("hardware counters must increase within each physical lane")
        lane.counter = counter
        counts["probes"] += 1
        if lane.anchor and counter - lane.anchor.counter > rate * MAX_GAP_S:
            lane.anchor = None
            lane.pending.clear()
        best = max(
            (c for c in probe["candidates"] if c[GATE] is True),
            key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
            default=None,
        )
        if best is None:
            counts["negative"] += 1
            if lane.anchor and probe["candidates"]:
                if len(lane.pending) == MAX_PENDING:
                    lane.pending.popleft()
                    counts["capacity_evictions"] += 1
                lane.pending.append((i, counter, probe))
                counts["largest_pending_lane"] = max(
                    counts["largest_pending_lane"], len(lane.pending)
                )
            continue
        current = Peak.from_candidate(probe, counter, best)
        if not (isfinite(current.cfo_hz) and isfinite(current.epoch)):
            raise ValueError("an admitted anchor must have finite phase and CFO")
        motion = change(lane.anchor, current, rate) if lane.anchor else None
        if motion is not None:
            counts["bracketed_negative_with_candidates"] += len(lane.pending)
            for index, middle_counter, middle in lane.pending:
                selected = select_middle(
                    middle, middle_counter, lane.anchor, current, motion, rate, sham
                )
                if selected is not None:
                    edits.append(
                        dict(
                            probe_index=index,
                            candidate_index=selected,
                            left_visit=lane.anchor.visit,
                            right_visit=current.visit,
                            delay_samples=counter - middle_counter,
                        )
                    )
        lane.pending.clear()
        lane.anchor = current
    return sorted(edits, key=lambda row: row["probe_index"]), dict(counts)
