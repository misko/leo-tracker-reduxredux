"""One paired stock refit after the failed curved and predictive track union."""

from time import process_time

import numpy as np

from leo.analysis.localization_v3 import event_position, family_weighting, history_policy
from leo.analysis.localization_v3.history_position import forecast_phase_mean, problem
from leo.analysis.localization_v3.retained_position import phase_widths
from tools.pipeline_eval.variants import algo08_collapsed, algo08_collapsed_salvage


def valid_entries(entries, owners, tracks):
    """Retain nominated identities only while their curved support still exists."""
    supported_bands = {(rx, channel > 4) for group in owners.values() for rx, channel in group}
    updated = []
    for entry in entries:
        track = tracks[entry["track_index"]]
        family = owners.get(entry["candidate_index"], set())
        if not family or (track["receiver"], track["channel"] > 4) not in supported_bands:
            return None
        updated.append(dict(entry, cross_receiver_curved_support=len({rx for rx, _ in family}) == 2))
    return updated


def repair_pair(proposal, half_width_km, *, fit_unchanged=False):
    scan, node, keep, entries, pair, model = (
        proposal[key] for key in ("scan", "node", "keep", "entries", "arms", "model")
    )
    start = process_time()
    c0 = pair["c0"]
    base = problem(scan, node, "c0", keep, c0["phase_reference"])
    remaining, curved_failed = algo08_collapsed.paired_mask(keep, base.rows, base.slices, pair)
    predictive_failed = {
        row["component"] for arm in algo08_collapsed.ARMS for row in pair[arm]["linear_gates"]
        if not row["compatible"]
    }
    entries_kept = [entry for entry in entries if entry["component"] not in predictive_failed]
    predictive_points = sum(entry["points"] for entry in entries
                            if entry["component"] in predictive_failed)
    info = dict(
        accepted=False, refits=0, removed_curved=curved_failed,
        removed_predictive=sorted(predictive_failed),
        removed_curved_points=int(keep.sum() - remaining.sum()),
        removed_predictive_points=predictive_points,
    )
    if not fit_unchanged and not curved_failed and not predictive_failed:
        return None, dict(info, reason="no_failed_tracks", cpu_s=process_time() - start)
    if not remaining.any():
        return None, dict(info, reason="no_remaining_curved_points", cpu_s=process_time() - start)

    # Stock physical mode selection uses the nominal track families. A nominal
    # multi-owner family with only one remaining owner cannot pass its gate.
    baseline = dict(arms={"c0": {"record": c0}})
    confidence = family_weighting.confidence_for(scan, node, remaining, baseline)
    powers, owners, _ = family_weighting.family_weights(
        base.rows, base.members, scan.tracks, confidence, "cross_rx_support",
        [int(remaining[sl].sum()) for sl in base.slices],
    )
    if any(len(owners[j]) == 1 for j in base.supported):
        return None, dict(info, reason="unqualified_orbital_support", cpu_s=process_time() - start)
    entries_kept = valid_entries(entries_kept, owners, scan.tracks)
    if entries_kept is None:
        return None, dict(info, reason="unqualified_predictive_support", cpu_s=process_time() - start)

    _, receipts = phase_widths(scan, base.labels)
    means = forecast_phase_mean(receipts, model["shrinkage"])
    prepared_cpu = process_time() - start
    attempted = {
        arm: event_position.refit(scan, node, remaining, arm, powers, means, model, [], entries_kept)
        for arm in algo08_collapsed.ARMS
    }
    accepted = history_policy.pair_passes(attempted, include_linear=bool(entries_kept),
                                          half_width_km=half_width_km)
    info.update(
        accepted=accepted, refits=1, cpu_s=process_time() - start, preparation_cpu_s=prepared_cpu,
        failed_tracks={arm: sorted(row["component"] for row in result["gates"]["tracks"] +
                                   result["linear_gates"] if not row["compatible"])
                       for arm, result in attempted.items()},
        phase_change_s={arm: row["final_phase_change_s"] for arm, row in attempted.items()},
    )
    result = dict(proposal, keep=remaining, entries=entries_kept, powers=powers, means=means,
                  arms=attempted)
    return (result if accepted else None), info


def screen_and_fit(incumbent, proposal, half_width_km):
    """Use the old endpoints for a single exact gate evaluation per arm."""
    scan, node, keep, entries, powers, means, model = (
        proposal[key] for key in ("scan", "node", "keep", "entries", "powers", "means", "model")
    )
    start = process_time()
    previous = problem(scan, incumbent["node"], "c0", incumbent["keep"])
    offered = problem(scan, node, "c0", keep)
    pair = {}
    for arm in algo08_collapsed.ARMS:
        record = incumbent["arms"][arm]
        references = dict(zip(previous.labels, record["phase_reference"], strict=True))
        reference = np.asarray([references.get(j, mean)
                                for j, mean in zip(offered.labels, means, strict=True)])
        model_arm = event_position.make_event_problem(
            scan, node, keep, arm, reference, powers, means, model, [],
        )
        event_position.attach_event_predictive(model_arm, entries, powers)
        event_position.cached(model_arm)
        pair[arm] = event_position.summary(model_arm, record["endpoint_east_north_km"], entries)
    gate_cpu = process_time() - start
    selected, info = repair_pair(dict(proposal, arms=pair), half_width_km, fit_unchanged=True)
    return selected, dict(info, fixed_endpoint_gate_cpu_s=gate_cpu, total_cpu_s=process_time() - start)


def binding(record_curved=None):
    return algo08_collapsed_salvage.binding(record_curved, repair=repair_pair)


def prefit_binding(record_curved=None):
    return algo08_collapsed_salvage.binding(record_curved, prefit=screen_and_fit)
