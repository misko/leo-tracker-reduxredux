"""Reduce fixed-owner setup work and try the exact signed likelihood near each ordinary arm."""

from functools import partial
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import event_position, family_weighting, position, scan as scan_kernel
from leo.analysis.localization_v3.history_policy import pair_passes
from leo.analysis.localization_v3.history_position import problem
from leo.analysis.localization_v3.retained_position import phase_widths
from tools.pipeline_eval.variants.compact_cavity_optimizer import INITIAL_RADIUS_KM, STOP_KM

import blind_joint_finish
import blind_joint_repair
import blind_joint_signed
import family_pool_closure
from blind_joint_finish import ARMS, elapsed, readout


def sensitive_rows(scan, node, keep):
    lookup = {track["key"]: i for i, track in enumerate(scan.tracks)}
    active, lanes = [], {}
    n = width = 0
    for row in node["seed"]["rows"]:
        if not row["active_curvature"]:
            continue
        i = lookup[row["component"]]
        track = scan.tracks[i]
        end = width + len(track["times"])
        chosen = keep[width:end]
        j = row["candidate_index"]
        if np.any(chosen):
            active.append((n, i, j, chosen))
            lanes.setdefault(j, set()).add((track["receiver"], track["channel"]))
        n += 1
        width = end
    if width != len(keep):
        raise ValueError("Confidence mask disagrees with the original fixed layout")
    sensitive = [(n, i, j, chosen) for n, i, j, chosen in active
                 if len(lanes[j]) >= 2 and len({rx for rx, _ in lanes[j]}) == 1]
    return n, len(active), sensitive


def minimum_confidence(scan, node, keep, baseline, *, receipts):
    """Return exact consumed values for the released cross-receiver support weights."""
    clocks = (process_time(), perf_counter())
    n, active, sensitive = sensitive_rows(scan, node, keep)
    confidence = np.zeros(n)
    points = 0
    if sensitive:
        saved = baseline["arms"]["c0"]["record"]
        p = problem(scan, node, "c0", keep, np.asarray(saved["phase_reference"]))
        point = np.asarray(saved["endpoint_east_north_km"])
        state = p.state(point)
        widths, _ = phase_widths(scan, list(range(len(scan.norads))))
        times = np.unique(np.concatenate([scan.tracks[i]["times"][mask] for _, i, _, mask in sensitive]))
        points = len(times)
        geometry = scan_kernel.prepare_phase_geometry(scan.sky, times)
        measurements = []
        for index, i, j, mask in sensitive:
            track = scan.tracks[i]
            q = track["rf_hz"] / 11.5e9
            y = (track["values"] - scan.hardware(track, state["beta"])
                 - q * scan.rx_basis[i] @ state["smooth"][track["receiver"] - 1])
            measurements.append((index, j, q, y[mask], np.searchsorted(times, track["times"][mask])))
        anchors = [point] + [np.clip(point + d, -scan.search_region.half_width_km, scan.search_region.half_width_km)
                             for d in (np.array([2, 0]), np.array([-2, 0]), np.array([0, 2]), np.array([0, -2]))]
        rows = np.array([index for index, *_ in measurements])
        exact = []
        for anchor in anchors:
            f, e, derivative = family_weighting.phase_linear_frequency(geometry, *scan.search_region.latlon(anchor))
            values = []
            for _, j, q, y, columns in measurements:
                scored = family_weighting.candidate_profile(y, q * f[:, columns], q * derivative[:, columns],
                                                            e[:, columns], scan.radio_sigma_hz, widths)
                values.append(family_weighting.competitor_confidence(scored["cost"], j)[0])
            exact.append(values)
        confidence[rows] = np.min(exact, axis=0)
    receipts.append(dict(active_tracks=active, scored_tracks=len(sensitive), compared_times=points,
                         full_times=len(scan.times), clocks=elapsed(*clocks)))
    return confidence


def propose(prepared, region, bound, measured, *, repair, cold_start=None):
    receipts = []
    measured["sensitive_confidence"] = receipts
    function = partial(minimum_confidence, receipts=receipts)
    with (patch.object(blind_joint_finish, "confidence_for", function),
          patch.object(blind_joint_repair, "confidence_for", function)):
        if cold_start is None:
            return family_pool_closure.propose(prepared, region, bound, measured, repair=repair)
        return blind_joint_finish.propose(prepared, region, bound, measured, repair=repair, cold_start=cold_start)


def warm_arm(candidate, means, arm):
    scan, node, keep, powers, entries, model = (candidate[key] for key in ("scan", "node", "keep", "powers", "entries", "model"))
    ordinary = candidate["arms"][arm]
    labels = sorted({row["candidate_index"] for row in node["seed"]["rows"]})
    start = point = np.asarray(ordinary["endpoint_east_north_km"])
    reference = np.clip(ordinary["state"]["phases"][labels], -15., 15.)
    history = []
    for _ in range(2):
        p = event_position.make_event_problem(scan, node, keep, arm, reference, powers, means, model, [])
        event_position.attach_event_predictive(p, entries, powers)
        event_position.cached(p)
        fit = position.fit(p, point, iterations=48)
        following = np.asarray(fit["parameters"])
        if (following.shape != (2,) or not np.isfinite(following).all() or not np.isfinite(fit["score"])
                or np.max(abs(following - start)) > INITIAL_RADIUS_KM
                or np.any(abs(following) > scan.search_region.half_width_km + 1e-8)):
            return None, "warm_fit_exterior_or_nonfinite"
        phase = np.clip(p.state(following)["phases"][p.labels], -15., 15.)
        if not np.isfinite(phase).all():
            return None, "warm_fit_nonfinite_phase"
        move, change = float(np.linalg.norm(following - point)), float(np.max(abs(phase - reference)))
        history.append(dict(fit=fit, movement_km=move, phase_change_s=change))
        if fit["stopped"] == "small_bounded_step" and move <= STOP_KM and change <= .01:
            record = event_position.summary(p, following, entries)
            return dict(record, history=history, final_phase_change_s=change), None
        point, reference = following, phase
    return None, "warm_fit_not_stationary_in_two_refreshes"


def fit_pair(candidate, means, measured):
    clocks = (process_time(), perf_counter())
    results, reasons = {}, {}
    for arm in ARMS:
        try:
            record, reason = warm_arm(candidate, means, arm)
        except (AssertionError, ValueError, np.linalg.LinAlgError) as error:
            record, reason = None, f"{type(error).__name__}: {error}"
        if record is not None:
            results[arm] = record
        reasons[arm] = reason
    passed = (len(results) == len(ARMS) and pair_passes(results, include_linear=True,
                                                       half_width_km=candidate["scan"].search_region.half_width_km))
    measured["warm_signed_fit"] = dict(accepted=bool(passed), reasons=reasons,
                                        finished_arms={arm: readout(value) for arm, value in results.items()},
                                        warm_clocks=elapsed(*clocks))
    if passed:
        return results
    clocks = (process_time(), perf_counter())
    try:
        return blind_joint_signed.fitted_pair(candidate, means)
    finally:
        measured["warm_signed_fit"]["cold_fallback_clocks"] = elapsed(*clocks)


def update(prepared, ordinary, measured):
    return blind_joint_signed.update(prepared, ordinary, measured, fit_pair=partial(fit_pair, measured=measured))
