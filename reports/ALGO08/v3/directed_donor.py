"""Paid-anchor extrapolation and one-to-one signed factor matching."""

from collections import Counter
from itertools import permutations
from math import remainder


ADC = 10_000_000
PERIOD = 40_000 / 3
NATIVE_WINDOW_PERIOD = 13_333
PHASE_LIMIT = 1000.
TIGHT = (400., 1.)
LOOSE = (2250., 6.)


def arrival_phase(counter, candidate):
    phase = (3 * counter % 40_000) / 3
    return (phase + candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]) % PERIOD


def extrapolate(counters, factors, correction):
    """Forecast a signed carrier and window-relative arrival from two older records."""
    left, right, target = counters
    if not 0 < right - left < target - left <= 8 * ADC:
        raise ValueError("Predictions require two strictly earlier anchors within eight seconds")
    fraction = (target - right) / (right - left)
    a, b, c = correction
    fa, fb = (r["fractional_tracking_cfo_hz"] for r in factors)
    y0, y1 = fa - a[0], fb - b[0]
    f = y1 + (y1 - y0) * fraction + c[0]
    p0 = arrival_phase(left, factors[0]) - a[1]
    p1 = arrival_phase(right, factors[1]) - b[1]
    movement = remainder(p1 - p0, PERIOD)
    if abs(movement) * ADC / (right - left) > PHASE_LIMIT:
        return None
    phase = (p1 + movement * fraction + c[1]) % PERIOD
    epoch = (phase - (3 * target % 40_000) / 3) % PERIOD
    return dict(cfo_hz=float(f), phase_sample=float(phase),
                epoch_sample=float(epoch % NATIVE_WINDOW_PERIOD))


def matching(counter, factors, queries, tolerance):
    """Maximize unique matched pairs, then minimize normalized errors."""
    hz_limit, time_limit = tolerance
    pairs = {}
    for i, query in enumerate(queries):
        for j, factor in enumerate(factors):
            cf_error = abs(query["cfo_hz"] - factor["fractional_tracking_cfo_hz"])
            phase_error = abs(remainder(query["phase_sample"] - arrival_phase(counter, factor), PERIOD))
            if cf_error <= hz_limit and (time_limit is None or phase_error <= time_limit):
                cost = (cf_error / hz_limit) ** 2
                if time_limit is not None:
                    cost += (phase_error / time_limit) ** 2
                pairs[i, j] = cost
    best_key, best = (0, 0., ()), ()
    for size in range(1, min(len(queries), len(factors)) + 1):
        for first in permutations(range(len(queries)), size):
            if tuple(sorted(first)) != first:
                continue
            for second in permutations(range(len(factors)), size):
                edges = tuple(zip(first, second, strict=True))
                if all(edge in pairs for edge in edges):
                    key = (-size, sum(pairs[e] for e in edges), edges)
                    if key < best_key:
                        best_key, best = key, edges
    return best


def best_factor(factors):
    return max(factors, key=lambda row: (row["fractional_margin"], -row["candidate_rank"]), default=None)


def coverage(rows, forecasts):
    report = {}
    selected = {"full_search": {}, "directed": {}}
    for cap in (1, 2):
        for name, (hz, timing) in (("tight", TIGHT), ("loose", LOOSE),
                                    ("signed_400", (400., None)), ("signed_2250", (2250., None))):
            counts = Counter()
            for slot, saved in forecasts.items():
                factors = rows[slot]["candidates"]
                offers = saved["queries"][:cap]
                matches = matching(rows[slot]["valid_start_counter"], factors, offers, (hz, timing))
                counts["queries"] += len(offers)
                counts["matched_factors"] += len(matches)
                counts["matched_lanes"] += bool(matches)
                counts["verified_factors"] += len(factors)
                counts["empty_saved_lanes"] += not factors
                counts["missed_factor_lanes"] += bool(factors and not matches)
                counts["nonempty_saved_lanes"] += bool(factors)
                for _, index in matches:
                    counts[f"rank_{factors[index]['candidate_rank']}"] += 1
                if name == "tight" and cap == 2:
                    recovered = best_factor([factors[j] for _, j in matches])
                    if recovered is not None:
                        selected["directed"][slot] = recovered
                    full = best_factor(factors)
                    if full is not None:
                        selected["full_search"][slot] = full
            counts["unmatched_queries"] = counts["queries"] - counts["matched_factors"]
            report[f"{cap}_{name}"] = dict(counts)
    return report, selected
