"""Audit the original continuation's causal predecessor limit on a saved event ledger."""

from collections import Counter, defaultdict, deque


def predecessor_support(events):
    """Count upper bounds without CFO or positive labels, then compare actual donor counts."""
    histories = defaultdict(lambda: deque(maxlen=12))
    eligible, observed = Counter(), [Counter(), Counter()]
    for row in events:
        if row["states"] == ["excluded_original"]*2:
            continue
        # Released continuation separates receiver, channel and exact RF.
        history = histories[tuple(row["stream"][1:])]
        now = row["sample"]
        if history and history[-1]["sample"] >= now:
            raise ValueError("The causal hardware counter must increase")
        recent = [prior for prior in history if 0 < now-prior["sample"] <= 80_000_000]
        if row["paid"]:
            eligible[sum(prior["paid"] for prior in recent)] += 1
        for radio, state in enumerate(row["states"]):
            if state == "measured_positive":
                observed[radio][sum(prior["states"][radio] == state for prior in recent)] += 1
        history.append(row)
    return dict(paid_visit_histogram=eligible, measured_positive_by_receiver=observed,
                can_have_three_measured_predecessors=sum(n for count, n in eligible.items() if count >= 3))
