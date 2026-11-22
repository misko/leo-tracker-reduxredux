"""Use one paired, warm regional likelihood after broad two-round discovery."""

from hashlib import sha256
import json
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import v5_core
from tools.pipeline_eval.variants.compact_cavity_optimizer import STOP_KM
from tools.pipeline_eval.variants.v5_screen_winner import SCREEN_ROUNDS
from tools.pipeline_eval.variants.v5_shared_search import shared_associations

ARMS = ("c0", "fitted_c")
ROUND_LIMIT = 5
GATE_LIMIT = 4
PHASE_SETTLED_S = 0.01
BOUNDARY = "Broad discovery and one warm paired curved-data likelihood with standard plot evidence"


def digest(data):
    return sha256((json.dumps(data, sort_keys=True) + "\n").encode()).hexdigest()


def nominate(scan):
    from leo.analysis.localization_v3.acceptance import actual_metrics
    from leo.analysis.localization_v3.position import refreshed

    with shared_associations(scan) as sharing:
        ranked = v5_core.ranked_initial_nodes(scan)
    branches = []
    for node in ranked[:3]:
        model, fit, _ = refreshed(scan, scan.radio_sigma_hz, node, "c0", rounds=SCREEN_ROUNDS)
        branches.append((node, model, fit))
    if not branches:
        return None
    winner = min(range(len(branches)), key=lambda rank: branches[rank][2]["score"])
    node, model, fit = branches[winner]
    point = fit["parameters"]
    state = model.state(point)
    seed = dict(rows=model.rows, state=state, aliases=model.alias, east_north_km=point, fits=[fit])
    gates = actual_metrics(model, seed, "c0", point)
    reference = np.clip(state["phases"][model.labels], -15, 15)
    metrics = dict(discovered_assignments=len(ranked), ranked_scores=[x[2]["score"] for x in branches],
                   chosen_rank=winner, sharing=dict(sharing), catalogue=len(scan.norads))
    return node, point, reference, model.reference, gates, metrics


def paired_mask(keep, rows, slices, pair):
    """Both calibration arms must retain the same track rows."""
    failed = {r["component"] for arm in ARMS for r in pair[arm]["gates"]["tracks"]
              if not r["compatible"]}
    kept = keep.copy()
    for row, sl in zip(rows, slices, strict=True):
        if row["component"] in failed:
            kept[sl] = False
    return kept, sorted(failed)


def refit(scan, node, keep, arm, powers, means, model, point, reference):
    from leo.analysis.localization_v3.event_position import cached, make_event_problem, summary
    from leo.analysis.localization_v3.position import fit

    history = []
    for _ in range(ROUND_LIMIT):
        problem = cached(make_event_problem(scan, node, keep, arm, reference, powers, means, model, []))
        result = fit(problem, point, iterations=48)
        following = np.asarray(result["parameters"])
        phase = np.clip(problem.state(following)["phases"][problem.labels], -15, 15)
        move = float(np.linalg.norm(following - point))
        change = float(np.max(abs(phase - reference)))
        history.append(dict(fit=result, phase_change_s=change, movement_km=move))
        point, reference = following, phase
        if change <= PHASE_SETTLED_S and move <= STOP_KM:
            break
    answer = summary(problem, point, [])
    return dict(answer, history=history, final_phase_change_s=change), (point, reference)


def infer(prepared, region, bound, stages, *, selected_evidence=None):
    from leo.analysis.localization_v3.family_weighting import confidence_for, family_weights
    from leo.analysis.localization_v3.history_policy import pair_passes, validate_history
    from leo.analysis.localization_v3.history_position import forecast_phase_mean, problem
    from leo.analysis.localization_v3.retained_position import phase_widths

    detail = dict(stage_s=stages)

    def withheld(reason):
        return dict(status="withheld", boundary=BOUNDARY, reason=reason, metrics=detail,
                    arms={arm: dict(latlon=None) for arm in ARMS})

    if prepared["status"] != "inputs_prepared":
        return withheld(prepared["status"])
    clock = perf_counter()
    noise = digest(prepared["noise"])
    first = v5_core.scan_context(prepared, region, noise, bound, "previous")
    selected = nominate(first)
    del first
    stages["initial"] = perf_counter() - clock
    if selected is None:
        return withheld("no_discovered_assignment")
    node, point, phase, screen_reference, gates, branch_metrics = selected
    detail.update(branch_metrics)
    clock = perf_counter()
    scan = v5_core.scan_context(prepared, region, noise, bound, "genuine_previous")
    base = problem(scan, node, "c0", None)
    keep, rejected = paired_mask(base.keep, base.rows, base.slices, {arm: dict(gates=gates) for arm in ARMS})
    detail["initial_rejected_tracks"] = rejected
    if not keep.any():
        return withheld("no_passing_calibration")
    starting = dict(arms={"c0": dict(record=dict(phase_reference=screen_reference,
                                                  endpoint_east_north_km=point))})
    confidence = confidence_for(scan, node, keep, starting)
    powers, _, _ = family_weights(base.rows, base.members, scan.tracks, confidence,
                                   "cross_rx_support", [int(keep[sl].sum()) for sl in base.slices])
    history = prepared["phase_history"]
    history_sha = digest(history)
    if prepared["phase_forecast"].get("history_sha256", history_sha) != history_sha:
        raise ValueError("causal phase history has changed")
    forecast = dict(prepared["phase_forecast"], history_sha256=history_sha)
    model, _ = validate_history(history, forecast, case="SCAN", origin_utc_ns=scan.origin_utc_ns,
                                cutoff_utc_ns=prepared["sky"]["metadata"]["cutoff_utc_ns"],
                                raw_sha256=history_sha)
    _, orbit_receipts = phase_widths(scan, base.labels)
    means = forecast_phase_mean(orbit_receipts, model["shrinkage"])
    stages["paired_preparation"] = perf_counter() - clock

    clock = perf_counter()
    warm = {arm: (point, phase) for arm in ARMS}
    detail["paired_gate_rounds"] = []
    for _ in range(GATE_LIMIT):
        pair = {}
        for arm in ARMS:
            pair[arm], warm[arm] = refit(scan, node, keep, arm, powers, means, model, *warm[arm])
        following, rejected = paired_mask(keep, base.rows, base.slices, pair)
        detail["paired_gate_rounds"].append(dict(
            active_points=int(keep.sum()), rejected_tracks=rejected,
            phase_rounds={arm: len(record["history"]) for arm, record in pair.items()},
            phase_changes_s={arm: record["final_phase_change_s"] for arm, record in pair.items()},
        ))
        if not rejected and pair_passes(pair, half_width_km=region.half_width_km):
            break
        if not following.any() or not rejected:
            break
        keep = following
    stages["paired_fit"] = perf_counter() - clock
    if rejected or not pair_passes(pair, half_width_km=region.half_width_km):
        return withheld("no_qualified_curved_pair")
    if selected_evidence is not None:
        selected_evidence(prepared, dict(scan=scan, node=node, keep=keep, entries=[], means=means,
                                         powers=powers, model=model, arms=pair), None)
    return dict(status="ok", boundary=BOUNDARY, metrics=detail, arms={
        arm: dict(latlon=list(record["endpoint_latlon"]), rf_rms_hz=float(record["RMS_hz"]))
        for arm, record in pair.items()
    })


def binding():
    return patch.object(v5_core, "infer", infer)
