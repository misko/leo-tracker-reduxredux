"""One original full-data likelihood on a shared mixture membership and checked gates."""

from copy import copy
from hashlib import sha256
import json

import numpy as np

from leo.analysis.localization_v3 import event_position
from leo.analysis.localization_v3.discovery import zero_state
from leo.analysis.localization_v3.family_weighting import family_weights
from leo.analysis.localization_v3.history_policy import pair_passes, validate_history
from leo.analysis.localization_v3.history_position import forecast_phase_mean, problem
from leo.analysis.localization_v3.position import fit
from leo.analysis.localization_v3.retained_position import phase_widths
from tools.pipeline_eval.variants import v5_core

from mixture_position import ARMS


def digest(value):
    return sha256((json.dumps(value, sort_keys=True) + "\n").encode()).hexdigest()


def reason_points(arm):
    return arm["families"] < 3 or arm["sampled_owner_points"] < 32 or arm["receivers"] != 2


def finish(prepared, region, bound, proposal):
    reasons = []
    if proposal["status"] != "complete":
        return dict(decision="fallback", reasons=[proposal["status"]]), None
    before = proposal["arms"]
    if reason_points(before["c0"]):
        return dict(decision="fallback", reasons=["weak_common_support"]), None
    if before["c0"]["sampled_owner_points"] < .8 * proposal["curved_points"] or before["c0"]["families"] < 6:
        reasons.append("insufficient_publishable_coverage")
    scan = copy(v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "genuine_previous"))
    membership = {row["key"]: row for row in before["c0"]["tracks"] if row["retained"]}
    scan.curved = [idx for idx in scan.curved if scan.tracks[idx]["key"] in membership]
    state, rows, aliases, confidence = zero_state(scan), [], [], []
    for idx in scan.curved:
        nomination = membership[scan.tracks[idx]["key"]]
        rows.append(dict(component=nomination["key"], active_curvature=True,
                         candidate_index=nomination["index"], candidate_norad=nomination["norad"]))
        aliases.append(nomination["alias"])
        confidence.append(nomination["weight"])
    node = dict(seed=dict(rows=rows, state=state), aliases=aliases)
    base = problem(scan, node, "c0", None)
    keep = base.keep
    powers, _, _ = family_weights(rows, base.members, scan.tracks, confidence, "cross_rx_support")
    history = prepared["phase_history"]
    history_sha = digest(history)
    raw_forecast = prepared["phase_forecast"]
    if raw_forecast.get("history_sha256", history_sha) != history_sha:
        raise ValueError("causal phase history has changed")
    forecast = dict(raw_forecast, history_sha256=history_sha)
    model, _ = validate_history(history, forecast, case="SCAN", origin_utc_ns=scan.origin_utc_ns,
                                cutoff_utc_ns=prepared["sky"]["metadata"]["cutoff_utc_ns"],
                                raw_sha256=history_sha)
    _, orbit_receipts = phase_widths(scan, base.labels)
    means = forecast_phase_mean(orbit_receipts, model["shrinkage"])
    references = {}
    for owner in base.labels:
        references[owner] = np.median([row["phase_s"] for row in membership.values() if row["index"] == owner])
    reference = np.asarray([references[j] for j in base.labels])
    paired, displays = {}, {}
    for arm in ARMS:
        physical = event_position.cached(event_position.make_event_problem(
            scan, node, keep, arm, reference, powers, means, model, [],
        ))
        start = np.asarray(before[arm]["east_north_km"])
        fitted = fit(physical, start, iterations=48)
        endpoint = np.asarray(fitted["parameters"])
        record = event_position.summary(physical, endpoint, [])
        posterior = np.clip(record["state"]["phases"][physical.labels], -15., 15.)
        change = float(np.max(abs(posterior - reference)))
        record.update(history=[dict(fit=fitted, phase_change_s=change)], final_phase_change_s=change)
        paired[arm] = record
        movement = float(np.linalg.norm(endpoint - start))
        margin = region.half_width_km - np.max(np.abs(endpoint))
        if movement > 1.:
            reasons.append(arm + "_motion")
        if margin < 1.:
            reasons.append(arm + "_face")
        gates = record["gates"]["tracks"]
        compatible = [row for row in gates if row["compatible"]]
        displays[arm] = dict(latlon=record["endpoint_latlon"], east_north_km=endpoint,
                             rf_rms_hz=record["RMS_hz"], objective=record["negative_twice_elbo"],
                             full_points=int(keep.sum()), qualified_points=sum(row["points"] for row in compatible),
                             qualified_tracks=len(compatible), total_tracks=len(gates),
                             phase_change_s=change, movement_km=movement, clearance_km=float(margin))
    if not pair_passes(paired, half_width_km=region.half_width_km):
        reasons.append("original_pair_gate")
    report = dict(decision="fallback" if reasons else "complete", reasons=reasons, arms=displays)
    signed = dict(scan=scan, node=node, keep=keep, entries=[], means=means, powers=powers, model=model, arms=paired)
    return report, (None if reasons else signed)
