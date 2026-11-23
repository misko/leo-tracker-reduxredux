"""Predict signed CFO on held opportunities from a first-pass owned RF model."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from statistics import median
from time import process_time

import numpy as np

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD, projected_receiver_basis


SECONDS = 60
CAP = 2
TOLERANCES_HZ = (400, 4550)


def signed_model(scan, record, lanes, satellites):
    """Predict phase-shifted causal Doppler plus the released receiver basis."""
    by_satellite = {int(n): j for j, n in enumerate(scan.norads)}
    labels = np.asarray([by_satellite[n] for n in satellites], dtype=int)
    times = np.asarray([row["time_s"] for row in lanes])
    state = record["state"]
    phase = np.clip(np.asarray(state["phases"]), -15., 15.)
    q = np.asarray([row["rf_hz"] / 11.5e9 for row in lanes])
    requested = times + phase[labels]
    domain = scan.sky["time_s"]
    valid = (requested >= domain[0]) & (requested <= domain[-1])
    result = np.full(len(lanes), np.nan)
    position = scan.search_region.latlon(record["endpoint_east_north_km"])
    frequency, elevation = paired_phase_frequency(scan.sky, times[valid], labels[valid], phase, *position)
    result[valid] = np.where(elevation >= 0., q[valid] * frequency, np.nan)
    by_lane = defaultdict(list)
    for index, lane in enumerate(lanes):
        by_lane[lane["receiver"], lane["channel"], lane["rf_hz"]].append(index)
    for (receiver, channel, rf), rows in by_lane.items():
        track = dict(receiver=receiver + 1, channel=channel, rf_hz=rf, times=times[rows])
        result[rows] += scan.hardware(track, state["beta"])
        result[rows] += rf / 11.5e9 * projected_receiver_basis(track["times"]) @ state["smooth"][receiver]
    return result


def local(times, target):
    start = bisect_left(times, target - SECONDS)
    end = bisect_right(times, target + SECONDS)
    if start == end:
        return None
    k = bisect_left(times, target, start, end)
    distance = min(abs(times[q] - target) for q in range(max(start, k - 1), min(end, k + 1)))
    return start, end, distance


def sorted_groups(raw):
    return {key: tuple(zip(*sorted(rows), strict=True)) for key, rows in raw.items()}


def anchor_tables(anchors, predicted):
    exact, subject, alias = (defaultdict(list) for _ in range(3))
    satellites = defaultdict(set)
    branches = defaultdict(set)
    for row, frequency in zip(anchors, predicted, strict=True):
        if not np.isfinite(frequency):
            continue
        time_s, norad, rx, rf = (row[k] for k in ("time_s", "norad", "receiver", "rf_hz"))
        residual = row["measured_cfo_hz"] - frequency
        branch = int(np.rint(residual / PERIOD))
        offset = float(residual - branch * PERIOD)
        exact[norad, rx, rf, branch].append((time_s, offset))
        subject[norad, rx].append((time_s, offset))
        alias[rx, rf, branch].append((time_s, offset))
        satellites[rx].add(norad)
        branches[rx, rf].add(branch)
    return sorted_groups(exact), sorted_groups(subject), sorted_groups(alias), satellites, branches


def rank(lane, tables, *, transfer):
    rx, rf, time_s = (lane[k] for k in ("receiver", "rf_hz", "time_s"))
    exact, subject, alias, satellites, branches = tables
    choices = []
    local_aliases = {branch: interval for branch in branches.get((rx, rf), ())
                     if (interval := local(alias[rx, rf, branch][0], time_s)) is not None}
    for norad in satellites.get(rx, ()):
        broad = subject[norad, rx]
        span = local(broad[0], time_s) if transfer else None
        for branch, supported in local_aliases.items():
            rows = exact.get((norad, rx, rf, branch))
            seen = None if rows is None else local(rows[0], time_s)
            if seen is not None:
                a, b, distance = seen
                choices.append((distance, a - b, norad, branch, rows[1], a, b))
            elif span is not None:
                a, b, distance = span
                x, y, _ = supported
                choices.append((distance, -min(b - a, y - x), norad, branch, broad[1], a, b))
    return [(norad, branch, median(residuals[a:b])) for _, _, norad, branch, residuals, a, b in
            sorted(choices, key=lambda row: row[:4])[:CAP]]


def propose(scan, record, metadata, sparse_rows):
    """Use only a sparse fit and admitted probe metadata, then seal per-lane candidates."""
    original = {row["observation_id"]: row for row in metadata}
    anchors = [dict(original[row["observation_id"]], norad=row["norad"],
                    measured_cfo_hz=row["measured_cfo_hz"]) for row in sparse_rows]
    if any(not row["searched"] for row in anchors):
        raise ValueError("An anchor used a held observation")
    start = process_time()
    frequencies = signed_model(scan, record, anchors, [row["norad"] for row in anchors])
    tables = anchor_tables(anchors, frequencies)
    results, clocks = {}, {}
    held = [row for row in metadata if not row["paid"]]
    for rule in ("exact_rf", "receiver_transfer"):
        clock = process_time()
        lanes, candidates = [], []
        for lane in held:
            for candidate in rank(lane, tables, transfer=rule == "receiver_transfer"):
                lanes.append(lane)
                candidates.append(candidate)
        output = defaultdict(list)
        if lanes:
            nominal = signed_model(scan, record, lanes, [row[0] for row in candidates])
            for lane, (norad, branch, offset), value in zip(lanes, candidates, nominal, strict=True):
                if np.isfinite(value):
                    output[lane["observation_id"]].append((norad, float(value + branch * PERIOD + offset)))
        results[rule] = dict(output)
        clocks[rule] = process_time() - clock
    return dict(proposals=results, cpu_s=process_time() - start, proposal_rule_cpu_s=clocks,
                finite_anchor_models=int(np.count_nonzero(np.isfinite(frequencies))))


def score(proposals, held_owner):
    """Score in original signed frequency units, leaving timing outside this trial."""
    counts = defaultdict(int)
    for oid, candidates in proposals.items():
        reference = held_owner.get(oid)
        if reference is None:
            continue
        norad, cfo_hz = reference
        counts["owned_lanes_with_proposal"] += 1
        counts["owner_in_shortlist"] += any(subject == norad for subject, _ in candidates)
        for threshold in TOLERANCES_HZ:
            compatible = [(label == norad, abs(value - cfo_hz) <= threshold) for label, value in candidates]
            counts[f"signed_{threshold}_hz"] += any(hit for _, hit in compatible)
            counts[f"owner_and_signed_{threshold}_hz"] += any(hit and right for right, hit in compatible)
    for key in ("owned_lanes_with_proposal", "owner_in_shortlist",
                *(f"{prefix}{threshold}_hz" for threshold in TOLERANCES_HZ
                  for prefix in ("signed_", "owner_and_signed_"))):
        counts.setdefault(key, 0)
    return dict(counts, held_owned=len(held_owner), all_proposal_lanes=len(proposals),
                all_proposals=sum(map(len, proposals.values())))
