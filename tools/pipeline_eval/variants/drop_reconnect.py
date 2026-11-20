"""Conservatively reconnect retained, unresolved pilots across known input gaps."""

from collections import defaultdict

import numpy as np
from numpy.polynomial.legendre import legval


def lane(row, native=False):
    if native:
        return row["native_receiver_id"], row["channel"], row["actual_rf_hz"]
    return row["receiver"], row["channel"], row["rf_hz"]


def fixed_links(prepared, gaps, config, active_curvature):
    """Extend existing private tracks without inventing a sample or moving an owner."""
    if not gaps:
        return prepared, []
    tracks = prepared["tracks"]
    occupied = {oid for track in tracks for oid in track["observation_ids"]}
    observations = prepared["observations"]
    rx = {row["receiver"]: row["native_receiver_id"] for row in observations}
    slots, gaps_by_lane = defaultdict(list), defaultdict(list)
    for index, track in enumerate(tracks):
        key = (rx[track["receiver"]], *lane(track)[1:])
        slots[key].append((index, track))
    for item in gaps:
        gaps_by_lane[item["receiver"], item["channel"], item["actual_rf_hz"]].append(item["time_s"])
    for times in gaps_by_lane.values():
        times.sort()
    proposed = defaultdict(list)
    for row in observations:
        oid = row["observation_id"]
        time, cfo = row["time_s"], row["measured_cfo_hz"]
        key = lane(row, native=True)
        missing = gaps_by_lane.get(key)
        if oid in occupied or not missing:
            continue
        nominations = []
        for index, track in slots[key]:
            position = np.searchsorted(track["times"], time)
            if position == 0 or position == len(track["times"]):
                continue
            left, right = track["times"][position - 1 : position + 1]
            if not left < time < right or right - left > config.max_gap_s:
                continue
            best = min(
                (
                    legval(
                        (time - piece["reference_time_s"]) / piece["time_scale_s"],
                        piece["coefficients_hz"],
                    )
                    for piece in track["pieces"]
                    if piece["start_s"] <= time <= piece["end_s"]
                ),
                key=lambda pred: abs(
                    (pred - cfo + config.alias_spacing_hz / 2) % config.alias_spacing_hz
                    - config.alias_spacing_hz / 2
                ),
                default=None,
            )
            if best is None:
                continue
            lifted = cfo + round((best - cfo) / config.alias_spacing_hz) * config.alias_spacing_hz
            residual = abs(best - lifted)
            if residual <= config.association_sigma * config.noise_sigma_hz:
                nominations.append((index, lifted, residual, left, right))
        if len(nominations) != 1:
            continue
        index, lifted, residual, left, right = nominations[0]
        tick = np.searchsorted(missing, left, side="right")
        if residual <= config.noise_sigma_hz and tick < len(missing) and missing[tick] < right:
            proposed[index].append((row, lifted, float(residual)))
    repaired, witness = list(tracks), []
    for index, gains in proposed.items():
        before = tracks[index]
        joined = sorted(
            zip(before["times"], before["values"], before["observation_ids"], strict=True),
            key=lambda row: row[0],
        )
        joined.extend((r["time_s"], lifted, r["observation_id"]) for r, lifted, _ in gains)
        joined.sort(key=lambda row: row[0])
        times, values, ids = zip(*joined, strict=True)
        after = dict(
            before, times=np.asarray(times), values=np.asarray(values), observation_ids=list(ids)
        )
        if active_curvature(before) != active_curvature(after):
            continue
        repaired[index] = after
        witness.extend(
            dict(id=r["observation_id"], track=before["key"], residual_hz=residual)
            for r, _, residual in gains
        )
    return dict(
        prepared, tracks=repaired, graph_points=prepared["graph_points"] + len(witness)
    ), witness
