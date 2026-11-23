"""Cold RF discovery, one curved salvage pass, and a matched joint position fit."""

from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import conservative_recovery, event_position, position
from leo.analysis.localization_v3.family_weighting import confidence_for, family_weights
from leo.analysis.localization_v3.history_policy import pair_passes, validate_history
from leo.analysis.localization_v3.history_position import forecast_phase_mean, problem
from leo.analysis.localization_v3.predictive_linear import select_entries
from leo.analysis.localization_v3.retained_position import phase_widths
from tools.pipeline_eval.variants import v5_core

from mixture_finish import digest
from mixture_trial import ARMS, elapsed


def cold_candidate(prepared, region, bound):
    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
    candidates = v5_core.ranked_initial_nodes(scan)[:3]
    fits, scores = [], []
    for node in candidates:
        model, fit, trace = position.refreshed(scan, scan.radio_sigma_hz, node, "c0", rounds=2, iterations=48)
        scores.append(float(fit["score"]) if np.isfinite(fit["score"]) else None)
        fits.append((node, np.asarray(fit["parameters"]),
                     dict(zip(model.labels, np.clip(trace[-1]["posterior_phase_s"], -15., 15.), strict=True))))
    valid = [i for i, score in enumerate(scores) if score is not None]
    if not valid:
        raise ValueError("No finite cold ranked assignment")
    selected = min(valid, key=scores.__getitem__)
    node, point, reference = fits[selected]
    return node, point, reference, dict(scores=scores, branch=selected + 1,
                                        east_north_km=point, latlon=region.latlon(point), catalogue=len(scan.norads))


def history_model(prepared, scan):
    raw = prepared["phase_history"]
    binding = digest(raw)
    forecast = prepared["phase_forecast"]
    if forecast.get("history_sha256", binding) != binding:
        raise ValueError("Causal history is different from the frozen digest")
    model, certified = validate_history(raw, dict(forecast, history_sha256=binding), case="SCAN",
                                        origin_utc_ns=scan.origin_utc_ns,
                                        cutoff_utc_ns=prepared["sky"]["metadata"]["cutoff_utc_ns"], raw_sha256=binding)
    return model, certified


def build_at(scan, node, keep, point, references, model):
    base = problem(scan, node, "c0", keep)
    _, orbit_receipts = phase_widths(scan, base.labels)
    means = forecast_phase_mean(orbit_receipts, model["shrinkage"])
    reference = np.array([references.get(j, mean) for j, mean in zip(base.labels, means, strict=True)])
    endpoint = dict(phase_reference=reference, endpoint_east_north_km=point)
    confidence = confidence_for(scan, node, base.keep, {"arms": {"c0": {"record": endpoint}}})
    powers, _, _ = family_weights(base.rows, base.members, scan.tracks, confidence, "cross_rx_support",
                                   [int(base.keep[sl].sum()) for sl in base.slices])
    exact = event_position.make_event_problem(scan, node, base.keep, "c0", reference, powers, means, model, [])
    return event_position.cached(exact), powers, means


def drop_failing(keep, rows, slices, gates):
    bad = {row["component"] for row in gates["tracks"] if not row["compatible"]}
    retained = keep.copy()
    for row, section in zip(rows, slices, strict=True):
        if row["component"] in bad:
            retained[section] = False
    return retained, sorted(bad)


def rescued_references(references, proposals):
    """Keep an existing family phase; use the median RF nomination for new families."""
    samples = {}
    for row in proposals:
        nomination = row["selected"]
        if nomination is not None:
            samples.setdefault(nomination["candidate_index"], []).append(nomination["phase_s"])
    result = dict(references)
    for label, phases in samples.items():
        result.setdefault(label, float(np.median(phases)))
    return result


def arm_finish(scan, node, keep, arm, reference, powers, means, model, entries, seed):
    point = np.asarray(seed)
    trace = []
    for _ in range(5):
        p = event_position.make_event_problem(scan, node, keep, arm, reference, powers, means, model, [])
        event_position.attach_event_predictive(p, entries, powers)
        event_position.cached(p)
        fitted = position.fit(p, point, iterations=48)
        following = np.asarray(fitted["parameters"])
        phase = np.clip(p.state(following)["phases"][p.labels], -15., 15.)
        move = float(np.linalg.norm(following - point))
        change = float(np.max(abs(phase - reference)))
        trace.append(dict(fit=fitted, phase_change_s=change, movement_km=move))
        point, reference = following, phase
        if change <= .01 and move <= .020:
            break
    record = event_position.summary(p, point, entries)
    record.update(history=trace, final_phase_change_s=trace[-1]["phase_change_s"])
    return record


def readout(record):
    curved = record["gates"]["tracks"]
    linear = record["linear_gates"]
    return dict(
        latlon=record["endpoint_latlon"], east_north_km=record["endpoint_east_north_km"],
        rf_rms_hz=record["RMS_hz"], objective=record["negative_twice_elbo"],
        curved_points=record["active_points"], linear_points=record["predictive_points"],
        compatible_curved_points=sum(t["points"] for t in curved if t["compatible"]),
        compatible_linear_points=sum(t["points"] for t in linear if t["compatible"]),
        failed_curved=[t["component"] for t in curved if not t["compatible"]],
        failed_linear=[t["component"] for t in linear if not t["compatible"]],
        phase_refreshes=len(record["history"]), final_phase_change_s=record["final_phase_change_s"],
        phase_last_site_move_km=record["history"][-1]["movement_km"],
    )


def propose(prepared, region, bound, measured, *, repair=None):
    if prepared["status"] != "inputs_prepared":
        return None, prepared["status"]
    cpu, wall = process_time(), perf_counter()
    node, point, reference, cold = cold_candidate(prepared, region, bound)
    measured.update(cold=cold, cold_clocks=elapsed(cpu, wall))
    cpu, wall = process_time(), perf_counter()
    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "genuine_previous")
    model, qualified = history_model(prepared, scan)
    base, powers, means = build_at(scan, node, None, point, reference, model)
    gates = conservative_recovery.retained_metrics(base, point)
    keep, rejected = drop_failing(base.keep, base.rows, base.slices, gates)
    offered = dict(full_curved=int(base.keep.sum()), initial_curved=int(keep.sum()),
                   cold_rejected_tracks=rejected, past_distribution_qualified=qualified)
    measured.update(support=offered, initial_gate_clocks=elapsed(cpu, wall))
    if not keep.any():
        return None, "no_curved_support"
    if not keep.all():
        cpu, wall = process_time(), perf_counter()
        screened, _, _ = build_at(scan, node, keep, point, reference, model)
        with patch.object(conservative_recovery, "repaired_fit",
                          lambda *_args, **_kwargs: (screened, dict(parameters=point), [], {})):
            node, restored, alternatives = conservative_recovery.salvage(scan, node, keep)
        offered.update(curved_restored=int((restored & ~keep).sum()), salvage=alternatives)
        keep = restored
        reference = rescued_references(reference, alternatives)
        measured["salvage_clocks"] = elapsed(cpu, wall)
    cpu, wall = process_time(), perf_counter()
    base, powers, means = build_at(scan, node, keep, point, reference, model)
    gates = conservative_recovery.retained_metrics(base, point)
    checked, rejected = drop_failing(keep, base.rows, base.slices, gates)
    offered.update(rechecked_curved=int(checked.sum()), second_curved_rejections=rejected)
    if not checked.any():
        measured["predictive_clocks"] = elapsed(cpu, wall)
        return None, "no_curved_support_after_salvage"
    if rejected:
        base, powers, means = build_at(scan, node, checked, point, reference, model)
        gates = conservative_recovery.retained_metrics(base, point)
    entries = select_entries(base, point, gates)
    offered.update(predictive_points=sum(entry["points"] for entry in entries), predictive_tracks=len(entries),
                   predictive_labels=[(entry["component"], entry["norad"], entry["alias"]) for entry in entries])
    measured["predictive_clocks"] = elapsed(cpu, wall)
    cpu, wall = process_time(), perf_counter()
    paired = {arm: arm_finish(scan, node, checked, arm, base.reference, powers, means, model, entries, point)
              for arm in ARMS}
    accepted = pair_passes(paired, include_linear=bool(entries), half_width_km=region.half_width_km)
    measured.update(finish={arm: readout(record) for arm, record in paired.items()}, finish_clocks=elapsed(cpu, wall),
                    pair_passes=accepted)
    signed = dict(scan=scan, node=node, keep=checked, entries=entries, means=means,
                  powers=powers, model=model, arms=paired)
    if not accepted and repair is not None:
        return repair(signed, region, measured)
    if not accepted:
        return None, "original_joint_pair_gate"
    return signed, None
