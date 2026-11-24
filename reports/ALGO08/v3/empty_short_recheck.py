"""Nominate exactly the first measured short empty after a supported carrier."""

from collections import defaultdict, deque
from hashlib import sha256
from math import isfinite
from pathlib import Path

from tools.pipeline_eval.variants import carrier_continuation


HORIZON = 80_000_000
OPPORTUNITIES = 12
MIN_VOTES = 3
CONTINUATION_SHA = "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee"


def lane(row):
    return row["visit_index"], row["receiver_id"]


def stream(row):
    return tuple(row[field] for field in ("edge", "receiver_id", "channel", "actual_rf_hz"))


def verified_votes():
    source = Path(carrier_continuation.__file__).read_bytes()
    if sha256(source).hexdigest() != CONTINUATION_SHA:
        raise ValueError("Use the unchanged released carrier-continuation vote source")
    return carrier_continuation.votes


def plan(rows, apertures):
    """Use only original candidate rows in acquisition order."""
    votes = verified_votes()
    history = defaultdict(lambda: deque(maxlen=OPPORTUNITIES))
    empties = []
    previous_lane = (-1, -1)
    for row, aperture in zip(rows, apertures, strict=True):
        lane_id = lane(row)
        if lane_id <= previous_lane or aperture not in ("full", "short"):
            raise ValueError("Expected unique original ordered receiver lanes")
        previous_lane = lane_id
        key = stream(row)
        past = history[key]
        now = row["valid_start_counter"]
        candidates = row["candidates"]
        if (past and now <= past[-1][0]) or len(candidates) > 1:
            raise ValueError("Expected causal one-candidate mixed history")
        if candidates and not (candidates[0]["passed_fractional_margin_gate"] is True
                               and isfinite(candidates[0]["fractional_tracking_cfo_hz"])):
            raise ValueError("Expected verified finite signed candidate history")
        if aperture == "short" and not candidates:
            last, recent = past[-1] if past else (None, ())
            older = [(time, cfo) for time, cfo in list(past)[:-1] if 0 < now-time <= HORIZON] if recent else []
            support = votes(recent[0], older, last) if older else 0
            empties.append(dict(lane=lane_id, stream=key, counter=now, last_positive_counter=last if recent else None,
                                prior_opportunities=len(older), prior_votes=support, triggered=support >= MIN_VOTES))
        current = tuple(candidate["fractional_tracking_cfo_hz"] for candidate in candidates)
        past.append((now, current))
    return empties
