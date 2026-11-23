"""Least native CPU required to preserve measured selections with full-or-empty lane calls."""

from collections import defaultdict

from tools.pipeline_eval.variants.carrier_continuation import Continuation


def history_key(row):
    return row["receiver_id"], row["channel"], row["actual_rf_hz"]


def replay(rows, keep):
    history = Continuation()
    selected = []
    for i, row in enumerate(rows):
        factors = row["candidates"] if i in keep else []
        _, choice, _ = history.select(dict(row, candidates=factors))
        selected.append(None if choice is None else factors[choice])
    return selected


def lane_optimum(rows, costs, expected):
    # Each occupied bit is a paid, nonempty visit. All intervening empty slots
    # still count toward the stock deque's twelve-opportunity eviction rule.
    history = Continuation()
    key = history_key(rows[0])
    width = history.by_lane[key].maxlen
    limit = (1 << width) - 1
    states = {0: (0, 0)}
    peak = 1
    frequencies = [tuple(f["fractional_tracking_cfo_hz"] for f in r["candidates"]) for r in rows]
    for i, row in enumerate(rows):
        next_states = {}
        for mask, (cost, schedule) in states.items():
            shifted = (mask << 1) & limit
            if expected[i] is None:
                prior = next_states.get(shifted)
                if prior is None or (cost, schedule) < prior:
                    next_states[shifted] = (cost, schedule)
            if not frequencies[i]:
                continue
            past = history.by_lane[key]
            past.clear()
            for distance in range(min(i, width), 0, -1):
                index = i - distance
                past.append((rows[index]["valid_start_counter"],
                             frequencies[index] if mask & (1 << (distance - 1)) else ()))
            _, choice, _ = history.select(row)
            if (None if choice is None else row["candidates"][choice]) == expected[i]:
                value = (cost + costs[i], schedule | (1 << i))
                prior = next_states.get(shifted | 1)
                if prior is None or value < prior:
                    next_states[shifted | 1] = value
        if not next_states:
            raise ValueError("Even the original schedule cannot reproduce the required continuation")
        states = next_states
        peak = max(peak, len(states))
    _, schedule = min(states.values())
    return [i for i in range(len(rows)) if schedule & (1 << i)], peak


def optimum(rows, costs):
    if len(rows) != len(costs) or any(type(cost) is not int or cost <= 0 for cost in costs):
        raise ValueError("Expected a positive native clock for every lane")
    expected = replay(rows, range(len(rows)))
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[history_key(row)].append(i)
    kept = set()
    peak = 0
    for indices in groups.values():
        local, size = lane_optimum([rows[i] for i in indices], [costs[i] for i in indices],
                                   [expected[i] for i in indices])
        kept.update(indices[j] for j in local)
        peak = max(peak, size)
    if replay(rows, kept) != expected:
        raise ValueError("Optimized full-or-empty schedule altered a published factor")
    return dict(lanes=len(rows), selected=sum(f is not None for f in expected), positive=sum(bool(r["candidates"]) for r in rows),
                full_ns=sum(costs), selected_only_floor_ns=sum(c for f, c in zip(expected, costs) if f is not None),
                positive_ns=sum(c for r, c in zip(rows, costs) if r["candidates"]), optimum_ns=sum(costs[i] for i in kept),
                kept_indices=sorted(kept), peak_states=peak)
