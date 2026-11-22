"""A conservative continuation test before the current CFO is measured."""

from math import inf, nextafter

MAX_SLOPE = 8000
SPAN_TICKS = 4_000_000
MAX_KNOWN_HZ = 2**30
# Each of two votes may differ from its prediction by 800 Hz. The added
# margin covers binary64 time, prediction and difference rounding.
PAIR_TOLERANCE = 1600 + 2**-10


def _narrow_slope(low, high, left_hz, right_hz, dt):
    difference = right_hz - left_hz
    lower = nextafter((difference - PAIR_TOLERANCE) / dt, -inf)
    upper = nextafter((difference + PAIR_TOLERANCE) / dt, inf)
    return max(low, lower), min(high, upper)


def history_allows_three(possible, now):
    """Enclose all possible votes given eligible, chronologically ordered visits.

    The possible visits share a lane and fall within the age horizon.
    Measured empty visits have already been omitted. An unresolved visit
    can supply one donor at any frequency.
    """
    if len(possible) < 3 or now - possible[0].counter < SPAN_TICKS:
        return False

    known = [past for past in possible if past.frequencies is not None]
    unknown_count = len(possible) - len(known)
    if unknown_count >= 2:
        return True
    if any(not abs(hz) <= MAX_KNOWN_HZ for past in known for hz in past.frequencies):
        return True

    old_unknown = unknown_count and any(
        past.frequencies is None and now - past.counter >= SPAN_TICKS for past in possible
    )
    for i, first in enumerate(known):
        if not old_unknown and now - first.counter < SPAN_TICKS:
            break
        for j in range(i + 1, len(known) if unknown_count else len(known) - 1):
            middle = known[j]
            first_gap = (middle.counter - first.counter) / 1e7
            for first_hz in first.frequencies:
                for middle_hz in middle.frequencies:
                    low, high = _narrow_slope(
                        -MAX_SLOPE, MAX_SLOPE, first_hz, middle_hz, first_gap,
                    )
                    if low > high:
                        continue
                    if unknown_count:
                        return True
                    for last in known[j + 1:]:
                        total_gap = (last.counter - first.counter) / 1e7
                        second_gap = (last.counter - middle.counter) / 1e7
                        for last_hz in last.frequencies:
                            left, right = _narrow_slope(low, high, first_hz, last_hz, total_gap)
                            if left <= right:
                                left, right = _narrow_slope(
                                    left, right, middle_hz, last_hz, second_gap,
                                )
                                if left <= right:
                                    return True
    return False
