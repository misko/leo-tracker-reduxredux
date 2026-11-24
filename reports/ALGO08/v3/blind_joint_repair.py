"""One matched-support repair after the original joint gates reject."""

from time import perf_counter, process_time

import numpy as np

from leo.analysis.localization_v3.family_weighting import confidence_for, family_weights
from leo.analysis.localization_v3.history_policy import pair_passes
from leo.analysis.localization_v3.history_position import forecast_phase_mean, problem
from leo.analysis.localization_v3.retained_position import phase_widths

from blind_joint_finish import ARMS, arm_finish, elapsed, readout


def failed_union(arms):
    return (
        {row["component"] for arm in ARMS for row in arms[arm]["gates"]["tracks"] if not row["compatible"]},
        {row["component"] for arm in ARMS for row in arms[arm]["linear_gates"] if not row["compatible"]},
    )


def small_rejection(counts):
    total_tracks, removed_tracks = counts["tracks"]
    return (removed_tracks > 0 and removed_tracks * 20 <= total_tracks
            and all(removed * 20 <= total for key, (total, removed) in counts.items() if key != "tracks"))


def retained_entries(entries, failed, groups, tracks):
    supported_bands = {(receiver, channel > 4) for group in groups.values() for receiver, channel in group}
    kept = []
    for entry in entries:
        target = tracks[entry["track_index"]]
        family = groups.get(entry["candidate_index"], set())
        if (entry["component"] not in failed and family
                and (target["receiver"], target["channel"] > 4) in supported_bands):
            kept.append(dict(entry, cross_receiver_curved_support=len({rx for rx, _ in family}) == 2))
    return kept


def repair_once(signed, region, measured, *, conditional_fallback=None):
    cpu, wall = process_time(), perf_counter()
    scan, node, keep, entries, first, model = (signed[k] for k in ("scan", "node", "keep", "entries", "arms", "model"))
    details = dict(attempted_refits=0)
    measured["repair"] = details

    def refuse(reason):
        details.update(status="rejected", reason=reason)
        measured["repair_prepare_clocks"] = elapsed(cpu, wall)
        return None, reason

    failed_curved, failed_linear = failed_union(first)
    base = problem(scan, node, "c0", keep, first["c0"]["phase_reference"])
    retained = keep.copy()
    groups = {}
    old_active_tracks, removed_curved_tracks = 0, 0
    for row, index, section in zip(base.rows, base.members, base.slices, strict=True):
        was_active = keep[section].any()
        old_active_tracks += int(was_active)
        if row["component"] in failed_curved:
            retained[section] = False
            removed_curved_tracks += int(was_active)
        elif was_active:
            track = scan.tracks[index]
            groups.setdefault(row["candidate_index"], set()).add((track["receiver"], track["channel"]))
    remain_entries = retained_entries(entries, failed_linear, groups, scan.tracks)
    lost_curves = int(keep.sum() - retained.sum())
    lost_linear = sum(entry["points"] for entry in entries) - sum(entry["points"] for entry in remain_entries)
    counts = dict(tracks=(old_active_tracks + len(entries), removed_curved_tracks + len(entries) - len(remain_entries)),
                  curved=(int(keep.sum()), lost_curves), predictive=(sum(entry["points"] for entry in entries), lost_linear))
    labels = base.labels
    width = (base.hardware.shape[1] + 1 + base.smooth.shape[1] + len(labels)
             + 3 * len(base.supported) + len(base.members))
    degrees = int(retained.sum()) - width - 2
    receiver_count = len({rx for group in groups.values() for rx, _ in group})
    details.update(rejection_counts=counts, residual_degrees_of_freedom=degrees, curved_families=len(groups),
                   receivers=receiver_count, removed_curved=sorted(failed_curved),
                   removed_predictive=sorted({entry["component"] for entry in entries}
                                             - {entry["component"] for entry in remain_entries}))
    if not small_rejection(counts):
        return refuse("repair_rejection_cap")
    if receiver_count != 2 or len(groups) < 2 or degrees <= 0:
        return refuse("repair_insufficient_calibration_support")
    if any(len(groups.get(j, ())) == 1 for j in base.supported):
        return refuse("repair_unqualified_orbital_support")
    for record in first.values():
        point = np.asarray(record["endpoint_east_north_km"])
        if point.shape != (2,) or not np.isfinite(point).all() or np.any(abs(point) > region.half_width_km + 1e-8):
            return refuse("repair_unqualified_region")
    confidence = confidence_for(scan, node, retained, {"arms": {"c0": {"record": first["c0"]}}})
    powers, _, _ = family_weights(base.rows, base.members, scan.tracks, confidence, "cross_rx_support",
                                   [int(retained[section].sum()) for section in base.slices])
    _, receipt = phase_widths(scan, labels)
    means = forecast_phase_mean(receipt, model["shrinkage"])
    measured["repair_prepare_clocks"] = elapsed(cpu, wall)
    cpu, wall = process_time(), perf_counter()
    repaired = {}
    for arm in ARMS:
        record = first[arm]
        reference = np.clip(record["state"]["phases"][labels], -15., 15.)
        repaired[arm] = arm_finish(scan, node, retained, arm, reference, powers, means, model,
                                   remain_entries, record["endpoint_east_north_km"])
    measured["repair_fit_clocks"] = elapsed(cpu, wall)
    accepted = pair_passes(repaired, include_linear=bool(remain_entries), half_width_km=region.half_width_km)
    details.update(attempted_refits=1, status="complete" if accepted else "rejected",
                   reason=None if accepted else "repair_original_joint_pair_gate",
                   finish={arm: readout(record) for arm, record in repaired.items()})
    candidate = dict(signed, keep=retained, entries=remain_entries, powers=powers, means=means, arms=repaired)
    if not accepted:
        if conditional_fallback is not None:
            return conditional_fallback(candidate, region, measured)
        return None, details["reason"]
    return candidate, None
