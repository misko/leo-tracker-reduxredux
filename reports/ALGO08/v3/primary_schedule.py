"""Exact three-action continuation oracle for paid and empty antenna opportunities."""

from collections import Counter, defaultdict, deque

from tools.pipeline_eval.variants.carrier_continuation import Continuation


SKIP, PRIMARY, FULL = range(3)
ACTIONS = ("skip", "primary", "full")
FREQUENCY = "fractional_tracking_cfo_hz"


def lane_key(row):
    return row["receiver_id"], row["channel"], row["actual_rf_hz"]


def replay_actions(rows, first, schedule):
    history = Continuation()
    selected = []
    for row, primary, action in zip(rows, first, schedule, strict=True):
        candidates = ([], primary, row["candidates"])[action]
        _, choice, _ = history.select(dict(row, candidates=candidates))
        selected.append(None if choice is None else candidates[choice])
    return selected


def minimum_history(rows, first, costs, required):
    key = lane_key(rows[0])
    history = Continuation()
    width = history.by_lane[key].maxlen
    states, peak = {(): (0, 0)}, 1
    counters = [row["valid_start_counter"] for row in rows]
    for i, row in enumerate(rows):
        first_set, full_set = first[i], row["candidates"]
        menus = [(SKIP, [], 0)]
        if first_set:
            menus.append((PRIMARY, first_set, costs[i][PRIMARY]))
        if full_set and (full_set != first_set or costs[i][FULL] < costs[i][PRIMARY]):
            menus.append((FULL, full_set, costs[i][FULL]))
        menus = [(a, f, c, tuple(x[FREQUENCY] for x in f)) for a, f, c in menus]
        pending = {}
        must_match = i in required
        reference = required.get(i)
        recent_counters = counters[max(i - width, 0):i]
        for frequencies, (cost, code) in states.items():
            for action, candidates, charge, added in menus:
                selected = None
                if must_match and candidates:
                    history.by_lane[key] = deque(zip(recent_counters, frequencies, strict=True), maxlen=width)
                    _, choice, _ = history.select(dict(row, candidates=candidates))
                    if choice is not None:
                        selected = candidates[choice]
                if must_match and selected != reference:
                    continue
                # Only the measured CFO list and the time survive into future
                # continuation. Current-slot scores do not persist.
                state = (*frequencies[-(width - 1):], added)
                candidate = (cost + charge, 3 * code + action)
                prior = pending.get(state)
                if prior is None or candidate < prior:
                    pending[state] = candidate
        if not pending:
            raise ValueError("The original continuation is infeasible in this history")
        states = pending
        peak = max(peak, len(states))
    _, code = min(states.values())
    result = [SKIP] * len(rows)
    for i in range(len(rows) - 1, -1, -1):
        code, result[i] = divmod(code, 3)
    return result, peak


def changes(reference, actual):
    changed = Counter(lost=0, gained=0, replaced=0)
    for before, after in zip(reference, actual, strict=True):
        if before != after:
            changed["gained" if before is None else "lost" if after is None else "replaced"] += 1
    return dict(changed)


def optimum(rows, first, costs, owned=None):
    if len(rows) != len(first) or len(rows) != len(costs):
        raise ValueError("Expected one measurement and cost tuple per opportunity")
    for row, factors, clocks in zip(rows, first, costs, strict=True):
        if (not isinstance(factors, list) or factors != [f for f in row["candidates"] if f["candidate_rank"] == 0]
                or len(factors) > 1 or len(clocks) != 3 or clocks[0] != 0
                or any(type(cost) is not int or cost <= 0 for cost in clocks[1:])):
            raise ValueError("Invalid primary-only parity or native clock")
    reference = replay_actions(rows, first, [FULL] * len(rows))
    required = set(range(len(rows))) if owned is None else set(owned)
    if any(not 0 <= i < len(rows) or (owned is not None and reference[i] is None) for i in required):
        raise ValueError("A solver-owned index lacks its original continuation factor")
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[lane_key(row)].append(i)
    schedule, peak = [SKIP] * len(rows), 0
    for indices in groups.values():
        actions, size = minimum_history(
            [rows[i] for i in indices], [first[i] for i in indices], [costs[i] for i in indices],
            {j: reference[i] for j, i in enumerate(indices) if i in required},
        )
        peak = max(peak, size)
        for i, a in zip(indices, actions, strict=True):
            schedule[i] = a
    selected = replay_actions(rows, first, schedule)
    if any(reference[i] != selected[i] for i in required):
        raise ValueError("Independent replay altered a required factor")
    counts = [schedule.count(a) for a in range(3)]
    return dict(actions=schedule, counts=dict(zip(ACTIONS, counts, strict=True)), peak_states=peak,
                selected=sum(point is not None for point in selected),
                required_rows=len(required), changed=changes(reference, selected),
                optimum_ns=sum(row[a] for row, a in zip(costs, schedule, strict=True)),
                full_ns=sum(row[FULL] for row in costs),
                primary_ns=sum(row[PRIMARY] for row in costs))
