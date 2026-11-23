"""Attach real future-supported factors without rebuilding the forward track graph."""

from collections import defaultdict
from copy import copy
from time import perf_counter, process_time

import numpy as np

from leo.analysis.localization_v3 import event_position
from leo.analysis.localization_v3.conservative_recovery import retained_metrics
from leo.analysis.localization_v3.history_policy import pair_passes
from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.localization_v3.predictive_linear import geometry_features, linear_geometry
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD, profile, projected_receiver_basis, whitening

from blind_joint_finish import ARMS, arm_finish, elapsed, readout
from local_future_inputs import MAX_GAP_S, lane


MAX_RESIDUAL_HZ = 450.


def memberships(signed, arm):
    record = signed["arms"][arm]
    maps = {}
    for role, groups in (("conditional", record["gates"]["tracks"]), ("predictive", record["linear_gates"])):
        for group in groups:
            if not group["compatible"] or group["component"] in maps:
                raise ValueError("Local repair needs a complete disjoint forward membership")
            maps[group["component"]] = (role, group["norad"], frozenset(group["observation_ids"]))
    return maps


def nominate(tracks, forward, future):
    slots = defaultdict(list)
    alive = set()
    for index, track in enumerate(tracks):
        if track["key"] in forward:
            role, _, keep = forward[track["key"]]
            active = track["times"][np.isin(track["observation_ids"], sorted(keep))]
            slots[(track["receiver"], track["channel"], track["rf_hz"])].append((index, role, active))
        alive.update(track["observation_ids"])
    for observation in future:
        oid, time = observation["observation_id"], observation["time_s"]
        if oid in alive:
            raise ValueError("Future acquisition overlaps the forward graph")
        for index, role, times in slots[lane(observation)]:
            if len(times) and min(abs(times-time)) <= MAX_GAP_S:
                yield index, role, observation


def extend_track(track, points):
    ids = track["observation_ids"] + [row["observation_id"] for row, _ in points]
    times = np.r_[track["times"], [row["time_s"] for row, _ in points]]
    values = np.r_[track["values"], [row["measured_cfo_hz"] + lift*PERIOD for row, lift in points]]
    order = np.argsort(times, kind="stable")
    if len(ids) != len(set(ids)) or np.any(np.diff(times[order]) <= 0):
        raise ValueError("An extended track must retain unique observations and epochs")
    return dict(track, observation_ids=[ids[i] for i in order], times=times[order], values=values[order],
                start_s=float(times[order[0]]), end_s=float(times[order[-1]]))


def enlarged(signed, active, additions):
    scan = copy(signed["scan"])
    scan.tracks, scan.white, scan.rx_basis = map(list, (scan.tracks, scan.white, scan.rx_basis))
    by_id = dict(scan.fixed_window_noise["per_observation_noise_sigma_hz"])
    for index, points in additions.items():
        track = scan.tracks[index] = extend_track(scan.tracks[index], points)
        scan.white[index] = whitening(track["times"])
        scan.rx_basis[index] = projected_receiver_basis(track["times"])
        for row, _ in points:
            sigma = scan.radio_sigma_hz
            model = scan.fixed_window_noise
            if model["extra_parameter_BIC_gain"] > 0:
                sigma = np.sqrt(np.clip(model["floor_sigma_hz"]**2 + model["strength_hz2"]/row["fractional_margin"], 40**2, 600**2))
            by_id[row["observation_id"]] = float(sigma)
    scan.fixed_window_noise = dict(scan.fixed_window_noise, per_observation_noise_sigma_hz=by_id)
    scan.times = np.unique(np.concatenate([track["times"] for track in scan.tracks]))
    scan.index = [np.searchsorted(scan.times, track["times"]) for track in scan.tracks]
    lookup = {track["key"]: i for i, track in enumerate(scan.tracks)}
    parts = []
    for row in signed["node"]["seed"]["rows"]:
        if row["active_curvature"]:
            i = lookup[row["component"]]
            ids = active[row["component"]] | {p["observation_id"] for p, _ in additions.get(i, ())}
            parts.append(np.isin(scan.tracks[i]["observation_ids"], sorted(ids)))
    entries = []
    for entry in signed["entries"]:
        track = scan.tracks[entry["track_index"]]
        entries.append(dict(entry, observation_ids=track["observation_ids"], points=len(track["times"])))
    return dict(signed, scan=scan, keep=np.concatenate(parts), entries=entries)


def build(signed, arm):
    record = signed["arms"][arm]
    problem = event_position.make_event_problem(signed["scan"], signed["node"], signed["keep"], arm,
                  record["phase_reference"], signed["powers"], signed["means"], signed["model"], [])
    return problem, np.asarray(record["endpoint_east_north_km"])


def predicted_linear(problem, entries, point, coefficients):
    if not entries:
        return {}
    view, values, _, _, slices = linear_geometry(problem, entries)
    geometry = geometry_features(view, point, 0.)
    residual = values - (view.q*geometry["intercept"] + geometry["features"] @ coefficients)
    return {e["track_index"]: (residual[sl], geometry["elevation"][sl]) for e, sl in zip(entries, slices, strict=True)}


def fixed_context(signed, arm):
    p, point = build(signed, arm)
    p = event_position.cached(p)
    coefficients = p.calculate(point)["coefficient"]
    state = p.state(point)
    curves = {p.scan.tracks[i]["key"]: frozenset(oid for oid, active in zip(p.scan.tracks[i]["observation_ids"], p.keep[sl], strict=True) if active)
              for i, sl in zip(p.members, p.slices, strict=True)}
    predictions = predicted_linear(p, signed["entries"], point, coefficients)
    biases = {i: float(profile(raw, np.zeros(len(raw)), *p.scan.white[i], bias_sigma=300.)["bias"][0])
              for i, (raw, _) in predictions.items()}
    return coefficients, state, curves, biases


def predict(signed, arm, context):
    coefficients, state, _, biases = context
    p, point = build(signed, arm)
    geometry = JointMarginal.calculate(p, point, geometry_only=True)
    raw = p.values - p.q*geometry["intercept"] - geometry["features"] @ coefficients
    geometry.update(coefficient=coefficients, conditional_residual_hz=raw)
    p.calculate, p.state = (lambda _: geometry), (lambda _: state)
    conditional = {i: (raw[sl], geometry["elevation"][sl]) for i, sl in zip(p.members, p.slices, strict=True)}
    predictive = predicted_linear(p, signed["entries"], point, coefficients)
    return p, point, conditional, predictive, biases


def lift_for(resid_elev_bias):
    lifts = []
    for residual, elevation, bias in resid_elev_bias:
        if elevation < 0 or not np.isfinite(residual-bias):
            return None
        lift = int(np.rint((bias-residual)/PERIOD))
        if abs(residual + lift*PERIOD - bias) > MAX_RESIDUAL_HZ:
            return None
        lifts.append(lift)
    return lifts[0] if len(set(lifts)) == 1 else None


def passing_tracks(signed, context, arm):
    problem, point, _, predictive, _ = predict(signed, arm, context)
    checked = {r["component"] for r in retained_metrics(problem, point)["tracks"] if r["compatible"]}
    for index, (raw, elevations) in predictive.items():
        track = signed["scan"].tracks[index]
        terms = profile(raw, np.zeros(len(raw)), *signed["scan"].white[index], bias_sigma=300.)
        noise = batch_noise_screen(terms["innovations"], track["times"])
        if (terms["rms"][0] <= MAX_RESIDUAL_HZ and abs(terms["bias"][0]) <= 3000
                and terms["alias"][0] == 0 and noise["noise_screen_pass"][0] and min(elevations) >= 0):
            checked.add(track["key"])
    return checked


def preserved(original, fitted, additions):
    if original.keys() != fitted.keys():
        return False
    return all((role, sat, ids | additions.get(key, set())) == fitted[key]
               for key, (role, sat, ids) in original.items())


def attach(prepared, signed, measured, future):
    started, wall = process_time(), perf_counter()
    notes = measured["local_future_repair"] = dict(future_opportunities=len(future), decision="unchanged")
    try:
        return proposed_attach(prepared, signed, notes, future)
    except (ValueError, AssertionError, np.linalg.LinAlgError) as exc:
        notes.update(decision="rejected", reason=f"{type(exc).__name__}: {exc}")
        return prepared, signed
    finally:
        notes["cost"] = elapsed(started, wall)


def proposed_attach(prepared, signed, notes, future):
    original = {arm: memberships(signed, arm) for arm in ARMS}
    if original["c0"] != original["fitted_c"]:
        raise ValueError("Forward calibrated memberships disagree")
    proposals = list(nominate(signed["scan"].tracks, original["c0"], future))
    notes["lane_time_hypotheses"] = len(proposals)
    if not proposals:
        return prepared, signed
    start, wall = process_time(), perf_counter()
    contexts = {arm: fixed_context(signed, arm) for arm in ARMS}
    active = contexts["c0"][2]
    shadow_additions = defaultdict(list)
    for index, _, row in proposals:
        shadow_additions[index].append((row, 0))
    shadow = enlarged(signed, active, shadow_additions)
    evaluated = {arm: predict(shadow, arm, contexts[arm]) for arm in ARMS}
    slots = {i: {oid: j for j, oid in enumerate(shadow["scan"].tracks[i]["observation_ids"])} for i in shadow_additions}
    paired = defaultdict(list)
    for i, role, row in proposals:
        oid = row["observation_id"]
        j = slots[i][oid]
        tests = []
        for _, _, conditional, predictive, biases in evaluated.values():
            residual, elevation = (conditional if role == "conditional" else predictive)[i]
            tests.append((residual[j], elevation[j], 0. if role == "conditional" else biases[i]))
        lift = lift_for(tests)
        if lift is not None:
            paired[oid].append((i, row, lift))
    additions = defaultdict(list)
    for candidates in paired.values():
        if len(candidates) == 1:
            index, row, lift = candidates[0]
            additions[index].append((row, lift))
    notes.update(paired_pointwise=sum(len(r) for r in paired.values()), ambiguous=sum(len(r)>1 for r in paired.values()))
    if additions:
        trial = enlarged(signed, active, additions)
        verified = set.intersection(*(passing_tracks(trial, contexts[arm], arm) for arm in ARMS))
        additions = {i: points for i, points in additions.items() if trial["scan"].tracks[i]["key"] in verified}
    notes["nomination_clocks"] = elapsed(start, wall)
    if not additions:
        return prepared, signed
    trial = enlarged(signed, active, additions)
    start, wall = process_time(), perf_counter()
    trial["arms"] = {arm: arm_finish(trial["scan"], trial["node"], trial["keep"], arm,
                       signed["arms"][arm]["phase_reference"], trial["powers"], trial["means"], trial["model"],
                       trial["entries"], signed["arms"][arm]["endpoint_east_north_km"]) for arm in ARMS}
    notes.update(refit_clocks=elapsed(start, wall), refitted={arm: readout(r) for arm, r in trial["arms"].items()})
    expected = {trial["scan"].tracks[i]["key"]: {row["observation_id"] for row, _ in points} for i, points in additions.items()}
    if (not pair_passes(trial["arms"], include_linear=bool(trial["entries"]), half_width_km=trial["scan"].search_region.half_width_km)
            or not all(preserved(original[arm], memberships(trial, arm), expected) for arm in ARMS)):
        notes.update(decision="rejected", reason="paired compatibility or fixed ownership")
        return prepared, signed
    rows = [row for points in additions.values() for row, _ in points]
    details = [{"component": trial["scan"].tracks[i]["key"], "norad": original["c0"][trial["scan"].tracks[i]["key"]][1],
                "role": original["c0"][trial["scan"].tracks[i]["key"]][0], "observation_id": row["observation_id"], "lift": lift}
               for i, points in additions.items() for row, lift in points]
    notes.update(decision="proposed", added=details)
    return dict(prepared, tracks=dict(prepared["tracks"], observations=prepared["tracks"]["observations"] + rows,
                                     tracks=trial["scan"].tracks)), trial
