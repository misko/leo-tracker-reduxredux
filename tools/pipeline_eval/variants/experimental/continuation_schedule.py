"""Find visits that can affect the released continuation rule using timestamps alone."""

from collections import defaultdict, deque


def inspect(probes):
    """Assume every earlier visit has any carrier needed to support a later one."""
    history = defaultdict(lambda: deque(maxlen=12))
    needed, publishable = set(), set()
    for index, row in enumerate(probes):
        lane = row["receiver_id"], row["channel"], row["actual_rf_hz"]
        past = history[lane]
        counter = row["valid_start_counter"]
        if past and counter <= past[-1][1]:
            raise ValueError("Non-increasing receiver counter")
        eligible = [(i, t) for i, t in past if counter - t <= 80_000_000]
        if len(eligible) >= 3 and counter - eligible[0][1] >= 4_000_000:
            publishable.add(index)
            needed.add(index)
            needed.update(i for i, _ in eligible)
        past.append((index, counter))
    return needed, publishable
