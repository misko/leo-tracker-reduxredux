"""Propose regional assignments on a time-spread sample, then restore every row."""

from copy import copy
from time import process_time

import numpy as np

from tools.pipeline_eval.variants import v5_core


# The residual-salvage coarse nominator already uses up to 16 observations.
TRACK_SAMPLES = 16
EARLY_ROUNDS = 2
TOTAL_ROUNDS = 5
INITIAL_BRANCHES = 3


def spread(times):
    """Keep the endpoints, then maximize distance from the closest retained time."""
    n = len(times)
    if n <= TRACK_SAMPLES:
        return np.arange(n)
    chosen = np.zeros(n, dtype=bool)
    chosen[[0, -1]] = True
    distance = np.minimum(times - times[0], times[-1] - times)
    for _ in range(TRACK_SAMPLES - 2):
        index = np.argmax(distance)  # Chronologically first in a tie.
        chosen[index] = True
        np.minimum(distance, np.abs(times - times[index]), out=distance)
    return np.flatnonzero(chosen)


def sampled_scan(full):
    """Preserve full-track curved eligibility and build coherent sampled lookups."""
    from leo.analysis.localization_v3 import scan

    if all(len(full.tracks[i]["times"]) <= TRACK_SAMPLES for i in full.curved):
        return full
    for key in ("previous_shape_cache", "causal_uncertainty_modes", "reference_motion_derivatives"):
        # These keys describe the causal orbit bank and support labels only.
        # Sampling changes the evaluation times, never the orbit modes.
        full.__dict__.setdefault(key, {})
    compact = copy(full)
    tracks = []
    for i in full.curved:
        t = full.tracks[i]
        keep = spread(t["times"])
        tracks.append(dict(t, times=t["times"][keep], values=t["values"][keep],
                           observation_ids=[t["observation_ids"][k] for k in keep]))
    compact.tracks = tracks
    compact.curved = list(range(len(tracks)))
    compact.groups = [(t["key"], [t]) for t in tracks]
    compact.times = np.unique(np.concatenate([t["times"] for t in tracks]))
    compact.index = [np.searchsorted(compact.times, t["times"]) for t in tracks]
    compact.geometry = scan.prepare_phase_geometry(compact.sky, compact.times)
    compact.white = [scan.whitening(t["times"]) for t in tracks]
    compact.ou = [scan.whitening(t["times"], correlated_sigma_hz=150.0,
                                 correlation_seconds=10.0) for t in tracks]
    compact.rx_basis = [full.rx_basis[i][np.searchsorted(full.tracks[i]["times"], t["times"])]
                        for i, t in zip(full.curved, tracks, strict=True)]
    return compact


def restore_node(scan, coarse):
    """Carry only the proposed owners and discrete aliases into the full likelihood."""
    from leo.analysis.localization_v3.discovery import zero_state

    tracks = {scan.tracks[i]["key"]: scan.tracks[i] for i in scan.curved}
    rows = []
    for row in coarse["seed"]["rows"]:
        t = tracks[row["component"]]
        j = int(row["candidate_index"])
        rows.append(dict(component=t["key"], candidate_index=j, candidate_norad=int(scan.norads[j]),
                         points=len(t["times"]), times_s=t["times"], active_curvature=True,
                         parts=1, split_at=-1))
    return dict(seed=dict(rows=rows, state=zero_state(scan)), aliases=coarse["aliases"])


def select(scan, detail):
    from leo.analysis.localization_v3 import discovery, position
    from leo.analysis.localization_v3.acceptance import actual_metrics

    started = process_time()
    sample = sampled_scan(scan)
    points = sum(len(scan.tracks[i]["times"]) for i in scan.curved)
    n = sum(len(sample.tracks[i]["times"]) for i in sample.curved)
    detail.update(full_curved_observations=points, sampled_curved_observations=n,
                  full_unique_times=len(scan.times), sampled_unique_times=len(sample.times),
                  sampled_context_cpu_s=process_time() - started)
    if sample is scan:
        detail["fallback"] = "all_curves_within_sample_budget"
        return v5_core.initial_selection(scan)

    started = process_time()
    nodes = v5_core.ranked_initial_nodes(sample)
    detail.update(discovery_cpu_s=process_time() - started, discovered_hypotheses=len(nodes))
    candidates = nodes[:INITIAL_BRANCHES]
    winner = None
    details = []
    clock = process_time()
    for coarse in candidates:
        _, early, history = position.refreshed(sample, sample.radio_sigma_hz, coarse, "c0",
                                               rounds=EARLY_ROUNDS)
        node = restore_node(scan, coarse)
        anchor = np.asarray(early["parameters"])
        reference = np.clip(history[-1]["posterior_phase_s"], -15, 15)
        for _ in range(TOTAL_ROUNDS - EARLY_ROUNDS):
            model = position.NormalPosition(scan, node, scan.radio_sigma_hz, False, reference=reference)
            fit = position.fit(model, anchor)
            anchor = np.asarray(fit["parameters"])
            state = model.state(anchor)
            reference = np.clip(state["phases"][model.labels], -15, 15)
        details.append(dict(sampled_score=float(early["score"]), full_score=float(fit["score"]),
                            full_points=int(fit["active_points"])))
        rank = len(details) - 1
        if winner is None or fit["score"] < winner[0]["score"]:
            winner = fit, model, node, state, rank
    fit, model, node, state, rank = winner
    point = np.asarray(fit["parameters"])
    checkpoint = dict(rows=model.rows, state=state, aliases=model.alias, east_north_km=point, fits=[fit])
    gate = actual_metrics(model, checkpoint, "c0", point)
    detail.update(fit_cpu_s=process_time() - clock, branches=details, selected_rank=rank,
                  initial_offset_km=point.tolist(), initial_full_accepted_points=gate["accepted_points"],
                  selected_signature=discovery.signature(node))
    if not gate["accepted_points"]:
        detail["fallback"] = "no_full_data_calibration"
        return v5_core.initial_selection(scan)
    result = dict(hypothesis=0, node=node, arms={"c0": {"metrics": gate}})
    return dict(choices=[result], selected_hypothesis=0), len(candidates)
