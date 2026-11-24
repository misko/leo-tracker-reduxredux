"""Price a single regional Doppler start with an independent bilateral forecast gate."""

import argparse
from collections import Counter, defaultdict
from itertools import product
from time import perf_counter, process_time

import numpy as np


ARMS = ("c0", "fitted_c")
MIN_RADIO = 12
CHALLENGE_KM = 2.


def timed(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def split(native):
    rows = native["source"]["probes"]
    lanes, held = Counter(), set()
    train, test = [], []
    for first, second in zip(rows[::2], rows[1::2], strict=True):
        key = first["edge"], first["channel"], first["actual_rf_hz"]
        visit = first["visit_index"]
        if (second["visit_index"] != visit or first["receiver_id"] == second["receiver_id"]
                or key != (second["edge"], second["channel"], second["actual_rf_hz"])):
            raise ValueError("Expected original signed stereo opportunities")
        use_held = lanes[key] % 5 == 2
        lanes[key] += 1
        if use_held:
            held.add(visit)
        for row in (first, second):
            empty = dict(row, candidates=[])
            train.append(empty if use_held else row)
            test.append(row if use_held else empty)
    training, held_view = (dict(native, source=dict(native["source"], probes=part)) for part in (train, test))
    return training, held_view, sorted(held)


def held_matches(tracks, nominated, observations):
    lanes = defaultdict(list)
    for n, track in enumerate(tracks):
        lanes[(track["receiver"], track["channel"], track["rf_hz"])].append((n, np.asarray(track["times"])))
    matched = defaultdict(list)
    for obs in observations:
        time = obs["time_s"]
        options = [n for n, times in lanes[obs["receiver"], obs["channel"], obs["actual_rf_hz"]]
                   if times[0] < time < times[-1] and np.min(abs(times-time)) <= 10.]
        if len(options) == 1 and options[0] in nominated:
            matched[options[0]].append(obs)
    return matched


def nominal_grid(scan):
    from leo.analysis.localization_v3 import scan as kernel
    from tools.pipeline_eval.variants.experimental.regional_reassignment import score_track

    region = scan.search_region
    step = region.width_km/4.
    points = [(0., 0.), *(p for p in product((-step, 0., step), repeat=2) if p != (0., 0.))]
    best, choices, best_value = None, {}, -np.inf
    metrics = []
    orbits = {int(n): i for i, n in enumerate(scan.norads)}
    for point in points:
        f, e, h = kernel.phase_linear_frequency(scan.geometry, *region.latlon(point))
        owners, score = {}, 0.
        for i in scan.curved:
            track, indices = scan.tracks[i], scan.index[i]
            q = track["rf_hz"]/11.5e9
            value, owner = score_track(track["values"], q*f[:, indices], e[:, indices], q*h[:, indices], scan.norads, len(orbits))
            score += value
            if owner is not None:
                owners[i] = orbits[owner]
        metrics.append(dict(xy=point, score=score, nominated=len(owners)))
        if score > best_value:
            best_value, best, choices = score, np.array(point), owners
    return best, choices, metrics


def anchored_models(scan, choices, held, anchor):
    from leo.analysis.localization_v3.discovery import zero_state
    from leo.analysis.localization_v3.families import AnchoredFamilies
    from leo.analysis.localization_v3.position import NormalPosition
    from leo.analysis.localization_v3.scan import ScanLikelihood

    indices, members = sorted(set(choices.values())), sorted(choices)
    keep = {idx: i for i, idx in enumerate(indices)}
    bank = {k: (v if k == "time_s" else v[indices]) for k, v in scan.sky.items()}
    # Unwrapped training track values are kept. Actual held CFO is carried only
    # in the external evaluation vectors, never in the fit input.
    train, expanded, held_mask, held_values, radios = [], [], [], [], []
    rows = []
    for idx in members:
        track = scan.tracks[idx]
        withheld = sorted(held[idx], key=lambda r: r["time_s"])
        train.append(track)
        times = np.r_[track["times"], [r["time_s"] for r in withheld]]
        order = np.argsort(times, kind="stable")
        latest = len(track["times"])
        full = dict(track, times=times[order], values=np.r_[track["values"], np.zeros(len(withheld))][order],
                    observation_ids=np.asarray(track["observation_ids"]+[r["observation_id"] for r in withheld])[order].tolist())
        expanded.append(full)
        hold = order >= latest
        held_mask.extend(hold)
        values = np.r_[np.zeros(latest), [r["measured_cfo_hz"] for r in withheld]][order]
        held_values.extend(values[hold])
        radios.extend([track["receiver"]]*len(withheld))
        rows.append(dict(component=track["key"], active_curvature=True, candidate_index=keep[choices[idx]]))

    def context(tracks):
        result = ScanLikelihood(tracks, bank, {str(n): scan.elements[str(n)] for n in bank["norad"]},
                        origin_utc_ns=scan.origin_utc_ns, regional_center=scan.center, noise=scan.fixed_window_noise,
                        search_region=scan.search_region, bound=scan.bound, previous_tle=scan.previous_tle,
                        previous_tle_sha256=scan.previous_tle_sha256, previous_sources=scan.previous_sources)
        result.curved = list(range(len(tracks)))
        return result

    first, final = context(train), context(expanded)
    node = dict(rows=rows, state=zero_state(first))
    aliases = AnchoredFamilies(first, node, "receiver_smooth", False, anchor).alias
    sigma = max(40., float(scan.radio_sigma_hz))
    mask = np.asarray(held_mask, dtype=bool)
    models = {arm: NormalPosition(final, dict(seed=node, aliases=aliases), sigma, arm == "fitted_c",
                                   keep=~mask, point_noise=np.full(len(mask), sigma)) for arm in ARMS}
    return models, mask, np.asarray(held_values), np.asarray(radios), sigma


def wrapped(values, period):
    return (np.asarray(values)+period/2) % period-period/2


def evaluate_arm(model, point, mask, measurements, radios, sigma):
    from leo.analysis.localization_v3.position import fit
    from leo.analysis.research.retained_track_likelihood import PERIOD

    result = fit(model, point, iterations=8)
    xy = np.asarray(result["parameters"])
    region = model.scan.search_region
    clearance = float(region.half_width_km - np.max(np.abs(xy)))

    def innovation(at):
        values = model.calculate(at)["conditional_residual_hz"][mask]
        errors = wrapped(measurements+values, PERIOD)
        return {str(rx): float((errors[radios == rx] ** 2).sum()) for rx in (1, 2)}

    baseline = innovation(xy)
    different = []
    if clearance >= CHALLENGE_KM:
        for shift in ((-CHALLENGE_KM, 0.), (CHALLENGE_KM, 0.), (0., -CHALLENGE_KM), (0., CHALLENGE_KM)):
            alternative = innovation(xy + shift)
            different.append(dict(shift_km=shift, log_gain={rx: (value-baseline[rx])/(2*sigma*sigma)
                                                           for rx, value in alternative.items()}))
    rms = {str(rx): float(np.sqrt(baseline[str(rx)]/(radios == rx).sum())) if (radios == rx).any() else None
           for rx in (1, 2)}
    return dict(east_north_km=xy, latlon=region.latlon(xy), clearance_km=clearance, train_rms_hz=result["residual_rms_hz"],
                held_rms_hz=rms, challengers=different)


def accepted(result):
    support = result["support"]
    failures = []
    if support["coverage"] < .5:
        failures.append("insufficient_held_coverage")
    if any(s["rows"] < MIN_RADIO or s["orbits"] < 2 for s in support["radio"].values()):
        failures.append("insufficient_independent_bilateral_predictions")
    for arm in ARMS:
        if arm not in result["arms"]:
            failures.append(arm+"_no_fit")
            continue
        fit = result["arms"][arm]
        if not np.isfinite(fit["clearance_km"]) or fit["clearance_km"] < CHALLENGE_KM:
            failures.append(arm+"_edge_ambiguity")
        if any(rms is None or not np.isfinite(rms) or rms > 2*support["sigma_hz"] for rms in fit["held_rms_hz"].values()):
            failures.append(arm+"_held_residual")
        if len(fit["challengers"]) != 4 or any(not np.isfinite(gain) or gain < 2
                for q in fit["challengers"] for gain in q["log_gain"].values()):
            failures.append(arm+"_weak_spatial_separation")
    return failures


def proposal(prepared, held_native, region, bound):
    from leo.analysis.localization_v3.tracks import winning_observations
    from tools.pipeline_eval.variants import v5_core

    start = process_time(), perf_counter()
    scan = v5_core.scan_context(prepared, region, None, bound, "previous")
    xy, choices, scoring = nominal_grid(scan)
    pre = timed(start)
    # Original held CFO enters only after choosing the training grid point.
    began = process_time(), perf_counter()
    relevant = [scan.tracks[idx] for idx in scan.curved]
    indexed = {index: choices[idx] for index, idx in enumerate(scan.curved) if idx in choices}
    observed, _ = winning_observations(held_native)
    by_index = held_matches(relevant, indexed, observed)
    mapped = {scan.curved[i]: rows for i, rows in by_index.items()}
    satellite_counts = {rx: {choices[idx] for idx in mapped if scan.tracks[idx]["receiver"] == rx} for rx in (1, 2)}
    held_counts = {rx: sum(len(rows) for idx, rows in mapped.items() if scan.tracks[idx]["receiver"] == rx) for rx in (1, 2)}
    count = sum(held_counts.values())
    support = dict(radio={str(rx): dict(rows=held_counts[rx], orbits=len(satellite_counts[rx])) for rx in (1, 2)},
                   coverage=(count/len(observed) if observed else 0.), original_held_rows=len(observed), matched_rows=count,
                   sigma_hz=max(40., float(scan.radio_sigma_hz)))
    aims = {}
    if mapped:
        # Preserve the held-matching evidence even if the training fit proves
        # geometrically ambiguous. Both arms have identical memberships.
        models, mask, values, radios, sigma = anchored_models(scan, {i: choices[i] for i in mapped}, mapped, xy)
        aims = {arm: evaluate_arm(models[arm], xy, mask, values, radios, sigma) for arm in ARMS}
    result = dict(arms=aims, support=support, mesh=scoring, chosen_mesh=xy, chosen_tracks=len(choices),
                  original_curves=len(scan.curved), fitted_tracks=len(mapped), region=dict(center=region.center, width_km=region.width_km),
                  mesh_clock=pre, fit_and_gate_clock=timed(began))
    reasons = accepted(result)
    return dict(result, gate="fallback" if reasons else "admit", gate_failures=reasons)
