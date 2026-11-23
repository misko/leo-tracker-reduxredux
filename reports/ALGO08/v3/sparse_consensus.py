"""Buffered signed-frequency votes on paid stereo opportunities."""

from collections import defaultdict


def paid_visits(rows):
    groups = defaultdict(list)
    for left, right in zip(rows[::2], rows[1::2], strict=True):
        keys = ("channel", "actual_rf_hz", "edge", "visit_index", "valid_start_counter")
        if ((left["receiver_id"], right["receiver_id"]) != (0, 1)
                or any(left[k] != right[k] for k in keys)):
            raise ValueError("Expected paired stereo visits")
        groups[tuple(left[k] for k in keys[:3])].append(left["visit_index"])
    return {v for rank, (_, visits) in enumerate(sorted(groups.items())) for v in visits[rank % 3::3]}


def choose(frequencies, neighbors):
    best, winner = (2, 0.0), None
    for rank, frequency in enumerate(frequencies):
        for seed_dt, seeds in neighbors:
            for seed in seeds:
                slope = (seed - frequency) / seed_dt
                if abs(slope) > 8000:
                    continue
                votes = []
                for dt, values in neighbors:
                    predicted = frequency + slope * dt
                    error = min((abs(value - predicted) for value in values), default=float("inf"))
                    if error <= 800:
                        votes.append((dt, 1 - error / 800))
                if len(votes) >= 3 and max(abs(dt) for dt, _ in votes) >= 0.4:
                    score = len(votes), sum(margin for _, margin in votes)
                    if score > best:
                        best, winner = score, rank
    return winner


def buffered(rows, paid, rate):
    result = [[] for _ in rows]
    lanes = defaultdict(list)
    for i, row in enumerate(rows):
        if row["visit_index"] in paid:
            key = tuple(row[k] for k in ("receiver_id", "channel", "actual_rf_hz", "edge"))
            frequencies = [c["fractional_tracking_cfo_hz"] for c in row["candidates"]]
            lanes[key].append((i, row["valid_start_counter"], frequencies))
    for lane in lanes.values():
        for j, (i, counter, frequencies) in enumerate(lane):
            if not frequencies:
                continue
            neighbors = [((other - counter) / rate, values)
                         for _, other, values in lane[max(0, j - 12):j + 13]
                         if 0 < abs(other - counter) <= 8 * rate and values]
            rank = choose(frequencies, neighbors)
            if rank is not None:
                result[i] = [rows[i]["candidates"][rank]]
    return result
