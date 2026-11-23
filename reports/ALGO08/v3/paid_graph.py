"""Use paid, signed receiver factors as alternatives in a Doppler track graph."""

from collections import defaultdict


def select(rows, paid, rate, config, fit_lane, use_graph):
    lanes = defaultdict(list)
    choices = [[] for _ in rows]
    stats = dict(paid_factors=0, ambiguous=0, tracks=0, duplicate_track_epochs=0, changed=0)
    for i, row in enumerate(rows):
        if row["visit_index"] not in paid:
            continue
        factors = [c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True]
        if factors:
            key = tuple(row[k] for k in ("receiver_id", "channel", "actual_rf_hz", "edge"))
            lanes[key].append((i, row["valid_start_counter"], factors))
            stats["paid_factors"] += len(factors)
            stats["ambiguous"] += int(len(factors) > 1)

    for lane in lanes.values():
        support = {}
        if use_graph and any(len(factors) > 1 for _, _, factors in lane):
            nodes = [(i, counter, c) for i, counter, factors in lane for c in factors]
            times = [(counter - lane[0][1]) / rate for _, counter, _ in nodes]
            graph = fit_lane(times, [c["fractional_tracking_cfo_hz"] for _, _, c in nodes], config)
            for track in graph["tracks"]:
                indices = track["indices"]
                epochs = {nodes[index][1] for index in indices}
                stats["tracks"] += 1
                stats["duplicate_track_epochs"] += len(indices) - len(epochs)
                for index in indices:
                    i, _, c = nodes[index]
                    support[i, c["candidate_rank"]] = len(epochs)
        for i, _, factors in lane:
            def margin(c):
                return c["fractional_margin"], -c["candidate_rank"]

            strongest = max(factors, key=margin)
            winner = max(factors, key=lambda c: (support.get((i, c["candidate_rank"]), 0), *margin(c)))
            stats["changed"] += int(winner is not strongest)
            choices[i] = [winner]
    return choices, stats
