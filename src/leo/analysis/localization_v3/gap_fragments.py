"""Native timing-gap fragments, validated against explicit observations.

Graph and calibration arrays stay unchanged; appended views use direct-time
predictive geometry. No old worker, discovery file or storage path is an input.
"""

import copy
import hashlib
import json

import numpy as np

from leo.analysis.research.retained_track_likelihood import (
    PERIOD,
    projected_receiver_basis,
    whitening,
)


def prepare_gap(context, inventory, observations, track_id):
    source = next(r for r in inventory["tracks"] if r["track_id"] == track_id)
    parent = context["scan"].tracks[source["track_index"]]
    lookup = {o["observation_id"]: o for o in observations}
    branches = []
    for a, b in partitions(parent["times"]):
        ids, values = parent["observation_ids"][a:b], parent["values"][a:b]
        lifts = np.rint(
            (values - np.array([lookup[o]["measured_cfo_hz"] for o in ids])) / PERIOD
        ).astype(int)
        branches.append(
            dict(
                branch_id=hashlib.sha256("\n".join(ids).encode()).hexdigest()[:20],
                parent_track_id=track_id,
                parent_index=source["track_index"],
                parent_key=parent["key"],
                observation_ids=ids,
                times_s=parent["times"][a:b],
                values_hz=values,
                alias_lifts=lifts,
                receiver=parent["receiver"],
                channel=parent["channel"],
                rf_hz=parent["rf_hz"],
                quality_status="inherited_graph_gap_fragment",
                pieces=parent["pieces"],
                RMS_hz=parent["residual_rms_hz"],
                large=True,
            )
        )
    return dict(
        protocol=dict(
            gap_s=5,
            minimum_points=12,
            minimum_span_s=10,
            selection=(
                "All eligible time-gap components; no frequency, residual, "
                "satellite or position filter"
            ),
            parent_observation_ids=parent["observation_ids"],
            retained_points=sum(len(b["observation_ids"]) for b in branches),
        ),
        branches=branches,
    )


def source_digest(source):
    def default(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(type(value).__name__)

    return hashlib.sha256(
        json.dumps(source, sort_keys=True, allow_nan=False, default=default).encode()
    ).hexdigest()


def gap_context(context, inventory, source, branch_id, observations):
    protocol = source["protocol"]
    if (protocol["gap_s"], protocol["minimum_points"], protocol["minimum_span_s"]) != (5, 12, 10):
        raise ValueError("wrong gap policy")
    branch = next(b for b in source["branches"] if b["branch_id"] == branch_id)
    parent = context["scan"].tracks[branch["parent_index"]]
    if (
        parent["key"] != branch["parent_key"]
        or parent["observation_ids"] != protocol["parent_observation_ids"]
    ):
        raise ValueError("gap parent changed")
    eligible = [parent["observation_ids"][a:b] for a, b in partitions(parent["times"])]
    if branch["observation_ids"] not in eligible:
        raise ValueError("not an eligible whole time-gap component")
    occupied = {o for r in inventory["policy"].values() for o in r["proposed_associated_ids"]}
    for p, _ in context["problems"].values():
        occupied.update(
            o
            for i, sl in zip(p.members, p.slices, strict=True)
            for o, k in zip(context["scan"].tracks[i]["observation_ids"], p.keep[sl], strict=True)
            if k
        )
    occupied.update(o for e in context["entries"] for o in e["observation_ids"])
    changed, i = append_branch(context["scan"], branch, observations, occupied)
    target = dict(
        track_id=branch_id,
        track_index=i,
        component=changed.tracks[i]["key"],
        current_large=True,
        observation_ids=branch["observation_ids"],
        gap_source_sha256=source_digest(source),
        original_graph_unchanged=True,
        gap_parent=branch["parent_key"],
    )
    return dict(context, scan=changed), target


def partitions(times, gap=5.0, minimum_points=12, minimum_span=10.0):
    t = np.asarray(times, float)
    if t.ndim != 1 or len(t) < 1 or (not np.isfinite(t).all()) or np.any(np.diff(t) <= 0):
        raise ValueError("finite strictly increasing times required")
    cuts = np.r_[0, np.flatnonzero(np.diff(t) > gap) + 1, len(t)]
    return [
        (int(a), int(b))
        for a, b in zip(cuts[:-1], cuts[1:], strict=True)
        if b - a >= minimum_points and t[b - 1] - t[a] >= minimum_span
    ]


def append_branch(scan, branch, observations, occupied):
    ids = branch["observation_ids"]
    lookup = {o["observation_id"]: o for o in observations}
    if len(ids) != len(set(ids)) or set(ids) & set(occupied):
        raise ValueError("native branch repeats or overlaps existing graph/associations")
    if not set(ids) <= set(lookup):
        raise ValueError("native branch contains unknown IDs")
    original = [lookup[o] for o in ids]
    t = np.asarray(branch["times_s"])
    y = np.asarray(branch["values_hz"])
    lifts = np.asarray(branch["alias_lifts"])
    if not np.array_equal(t, [o["time_s"] for o in original]) or np.any(np.diff(t) <= 0):
        raise ValueError("native branch timestamps differ or are not increasing")
    if not np.allclose(
        y, np.array([o["measured_cfo_hz"] for o in original]) + PERIOD * lifts, rtol=0, atol=1e-07
    ):
        raise ValueError("native branch changes measured CFO")
    if any(
        (o["receiver"], o["channel"], o["actual_rf_hz"])
        != (branch["receiver"], branch["channel"], branch["rf_hz"])
        for o in original
    ):
        raise ValueError("native branch mixes RF/RX/channel lanes")
    changed = copy.copy(scan)
    changed.tracks = list(scan.tracks)
    changed.white = list(scan.white)
    changed.rx_basis = list(scan.rx_basis)
    index = len(changed.tracks)
    case = scan.tracks[0]["source_id"]
    key = f"{case}-RX{branch['receiver']}-CH{branch['channel']}-NATIVE-{branch['branch_id']}"
    track = dict(
        key=key,
        source_id=case,
        receiver=branch["receiver"],
        channel=branch["channel"],
        bank="CH1-4" if branch["channel"] <= 4 else "CH5-8",
        rf_hz=branch["rf_hz"],
        observation_ids=ids,
        times=t,
        values=y,
        quality_status=branch["quality_status"],
        pieces=branch["pieces"],
        start_s=float(t[0]),
        end_s=float(t[-1]),
        residual_rms_hz=branch["RMS_hz"],
    )
    changed.tracks.append(track)
    changed.white.append(whitening(t))
    changed.rx_basis.append(projected_receiver_basis(t))
    return (changed, index)
