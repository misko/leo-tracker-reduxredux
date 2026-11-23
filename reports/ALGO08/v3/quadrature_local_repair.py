"""Screen failed full-data quadrature targets against surviving causal RF families."""

from copy import deepcopy
from time import perf_counter, process_time

import numpy as np

from leo.analysis.localization_v3 import event_position
from leo.analysis.localization_v3.acceptance import conditional_gate
from leo.analysis.localization_v3.history_policy import pair_passes
from leo.analysis.localization_v3.predictive_linear import geometry_features, linear_geometry
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile, whitening

from blind_joint_finish import ARMS, arm_finish, build_at, elapsed, readout
from blind_joint_repair import failed_union, retained_entries, small_rejection


def scores(raw, elevations, times, *, predictive):
    terms = profile(np.zeros(len(times)), -raw, *whitening(times),
                    bias_sigma=300. if predictive else 1000.)
    passing = ((terms["rms"] <= 450) & (np.abs(terms["bias"]) <= 3000)
               & (elevations.min(axis=1) >= 0)
               & batch_noise_screen(terms["innovations"], times)["noise_screen_pass"])
    if not predictive:
        for i in np.flatnonzero(passing):
            passing[i] = conditional_gate(terms["residual"][i], times)["compatible"]
    return [dict(alias=int(terms["alias"][i]), cost=float(terms["cost"][i]),
                 rms_hz=float(terms["rms"][i]), compatible=bool(passing[i]))
            for i in range(len(raw))]


def common_nomination(labels, arms):
    compatible = []
    for j, values in zip(labels, zip(*(arms[arm] for arm in ARMS), strict=True), strict=True):
        if all(v["compatible"] for v in values) and values[0]["alias"] == values[1]["alias"]:
            compatible.append(dict(label=j, alias=values[0]["alias"], cost=max(v["cost"] for v in values)))
    return min(compatible, key=lambda row: (row["cost"], row["label"]), default=None), compatible


def calibration(signed, layout, failed):
    scan, node, keep, powers, means, model = (signed[k] for k in ("scan", "node", "keep", "powers", "means", "model"))
    healthy = keep.copy()
    groups = {}
    for row, i, section in zip(layout.rows, layout.members, layout.slices, strict=True):
        track = scan.tracks[i]
        if row["component"] in failed:
            healthy[section] = False
        if healthy[section].any():
            groups.setdefault(row["candidate_index"], set()).add((track["receiver"], track["channel"]))
    arms = {}
    for arm, saved in signed["arms"].items():
        position = saved["endpoint_east_north_km"]
        problem = event_position.make_event_problem(scan, node, healthy, arm, saved["phase_reference"], powers, means, model, [])
        arms[arm] = (problem, position, problem.calculate(position)["coefficient"])
    return groups, arms


def alternatives(index, mask, labels, arm_contexts, *, predictive):
    arm_results = {}
    requests = [dict(track_index=index, candidate_index=j, alias=0) for j in labels]
    for arm, (problem, position, coefficient) in arm_contexts.items():
        view, raw, _, _, _ = linear_geometry(problem, requests)
        geometry = geometry_features(view, position, 0.)
        prediction = view.q * geometry["intercept"] + geometry["features"] @ coefficient
        times = problem.scan.tracks[index]["times"][mask]
        arm_results[arm] = scores((raw - prediction).reshape(len(labels), -1)[:, mask],
                                  geometry["elevation"].reshape(len(labels), -1)[:, mask], times,
                                  predictive=predictive)
    return arm_results


def losses(scan, layout, keep, entries, failed_curved, failed_linear, nominations):
    groups = {}
    total_curves = removed_curves = removed_points = 0
    for row, index, section in zip(layout.rows, layout.members, layout.slices, strict=True):
        points = int(keep[section].sum())
        if not points:
            continue
        total_curves += 1
        key = row["component"]
        replacement = nominations.get(key)
        if key in failed_curved and replacement is None:
            removed_curves += 1
            removed_points += points
        else:
            track = scan.tracks[index]
            j = row["candidate_index"] if replacement is None else replacement["label"]
            groups.setdefault(j, set()).add((track["receiver"], track["channel"]))
    updated = updated_entries(entries, nominations)
    retained = retained_entries(updated, failed_linear - nominations.keys(), groups, scan.tracks)
    pred = sum(e["points"] for e in entries)
    return dict(tracks=(total_curves + len(entries), removed_curves + len(entries) - len(retained)),
                curved=(int(keep.sum()), removed_points), predictive=(pred, pred - sum(e["points"] for e in retained)))


def updated_entries(entries, nominations):
    return [dict(e, candidate_index=nominations[e["component"]]["label"], norad=nominations[e["component"]]["norad"],
                 alias=nominations[e["component"]]["alias"]) if e["component"] in nominations else e for e in entries]


def exact_pair(signed, nominations, region):
    scan, keep, model = (signed[k] for k in ("scan", "keep", "model"))
    node = deepcopy(signed["node"])
    old_labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
    for i, row in enumerate(node["seed"]["rows"]):
        chosen = nominations.get(row["component"])
        if chosen is not None:
            row.update(candidate_index=chosen["label"], candidate_norad=chosen["norad"])
            node["aliases"][i] = chosen["alias"]
    entries = updated_entries(signed["entries"], nominations)
    new_labels = {r["candidate_index"] for r in node["seed"]["rows"]}
    if any(e["candidate_index"] not in new_labels for e in entries):
        return dict(status="unavailable_predictive_label")
    point = signed["arms"]["c0"]["endpoint_east_north_km"]
    reference = dict(zip(old_labels, signed["arms"]["c0"]["phase_reference"], strict=True))
    base, powers, means = build_at(scan, node, keep, point, reference, model)
    paired = {}
    for arm, saved in signed["arms"].items():
        phases = dict(zip(old_labels, saved["phase_reference"], strict=True))
        initial = np.array([phases[j] for j in base.labels])
        paired[arm] = arm_finish(scan, node, keep, arm, initial, powers, means, model, entries,
                                 saved["endpoint_east_north_km"])
    accepted = pair_passes(paired, include_linear=bool(entries), half_width_km=region.half_width_km)
    return dict(status="qualified" if accepted else "rejected", arms={a: readout(r) for a, r in paired.items()})


def diagnose(signed, region):
    from leo.analysis.localization_v3.history_position import problem

    cpu, wall = process_time(), perf_counter()
    scan, node, keep, entries = (signed[k] for k in ("scan", "node", "keep", "entries"))
    failed_curved, failed_linear = failed_union(signed["arms"])
    layout = problem(scan, node, "c0", keep, signed["arms"]["c0"]["phase_reference"])
    groups, arms = calibration(signed, layout, failed_curved)
    original = losses(scan, layout, keep, entries, failed_curved, failed_linear, {})
    calibration_time = elapsed(cpu, wall)

    targets, nominations = {}, {}
    cpu, wall = process_time(), perf_counter()

    def screen(key, index, mask, label, alias, *, predictive):
        track = scan.tracks[index]
        band_supported = any((track["receiver"], track["channel"] > 4) == (rx, channel > 4)
                             for group in groups.values() for rx, channel in group)
        labels = sorted(groups) if not predictive or band_supported else []
        observations = np.asarray(track["observation_ids"])[mask].tolist()
        offered = dict(role="predictive" if predictive else "conditional", points=len(observations),
                       observation_ids=observations, incumbent=dict(norad=int(scan.norads[label]), alias=alias))
        if labels:
            scores_by_arm = alternatives(index, mask, labels, arms, predictive=predictive)
            chosen, common = common_nomination(labels, scores_by_arm)
            offered.update(arms={arm: [dict(score, norad=int(scan.norads[j])) for j, score in zip(labels, values, strict=True)]
                                 for arm, values in scores_by_arm.items()}, compatible=common)
            if chosen is not None:
                nominations[key] = dict(chosen, norad=int(scan.norads[chosen["label"]]))
        targets[key] = offered

    for row, i, section, alias in zip(layout.rows, layout.members, layout.slices, layout.alias, strict=True):
        if row["component"] in failed_curved:
            screen(row["component"], i, keep[section], row["candidate_index"], alias, predictive=False)
    for e in entries:
        if e["component"] in failed_linear:
            screen(e["component"], e["track_index"], slice(None), e["candidate_index"], e["alias"], predictive=True)
    remaining = losses(scan, layout, keep, entries, failed_curved, failed_linear, nominations)
    feasible = not any(r[1] for r in remaining.values()) or small_rejection(remaining)
    screen_time = elapsed(cpu, wall)
    result = dict(original_losses=original, optimistic_losses=remaining, optimistic_cap_pass=feasible,
                  retained_families=len(groups), targets=targets, nominations=nominations,
                  calibration_clocks=calibration_time, screen_clocks=screen_time)
    if feasible:
        cpu, wall = process_time(), perf_counter()
        result.update(exact_pair=exact_pair(signed, nominations, region), exact_pair_clocks=elapsed(cpu, wall))
    return result
