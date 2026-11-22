"""Nominate masked tracks once from the collapsed curved incumbent."""

from functools import partial
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import algo08_collapsed, algo08_collapsed_linear, v5_core


def recover(signed, half_width_km, *, repair=None, prefit=None):
    from leo.analysis.localization_v3 import conservative_recovery
    from leo.analysis.localization_v3.event_position import make_event_problem, refit
    from leo.analysis.localization_v3.family_weighting import confidence_for, family_weights
    from leo.analysis.localization_v3.history_policy import pair_passes
    from leo.analysis.localization_v3.history_position import forecast_phase_mean
    from leo.analysis.localization_v3.predictive_linear import select_entries
    from leo.analysis.localization_v3.retained_position import phase_widths

    scan, node, keep = (signed[k] for k in ("scan", "node", "keep"))
    info = dict(masked_points=int((~keep).sum()), recovered_points=0, accepted=False)
    if keep.all():
        result, linear = algo08_collapsed_linear.admit(signed, half_width_km)
        return result, dict(info, linear=linear)

    powers, means, model = (signed[k] for k in ("powers", "means", "model"))
    c0 = signed["arms"]["c0"]
    point = c0["endpoint_east_north_km"]
    base = make_event_problem(scan, node, keep, "c0", c0["phase_reference"],
                              powers, means, model, [])

    # The stock salvage proposal/qualification uses p.state(x). Reuse the
    # selected curved fit for that input in this one nomination.
    with patch.object(conservative_recovery, "repaired_fit",
                      lambda *_a, **_kw: (base, dict(parameters=point), [], {})):
        replacement, following, trims = conservative_recovery.salvage(scan, node, keep)
    info["recovered_points"] = int((following & ~keep).sum())
    info["selected_trims"] = sum(row["selected"] is not None for row in trims)
    if not info["recovered_points"]:
        result, linear = algo08_collapsed_linear.admit(signed, half_width_km)
        return result, dict(info, linear=linear)

    labels = sorted({row["candidate_index"] for row in replacement["seed"]["rows"]})
    _, receipts = phase_widths(scan, labels)
    new_means = forecast_phase_mean(receipts, model["shrinkage"])
    known_references = dict(zip(base.labels, base.reference, strict=True))
    reference = np.array([known_references.get(j, old) for j, old in zip(labels, new_means, strict=True)])
    confidence_record = dict(arms={"c0": dict(record=dict(phase_reference=reference,
                                                           endpoint_east_north_km=point))})
    confidence = confidence_for(scan, replacement, following, confidence_record)
    updated = make_event_problem(scan, replacement, following, "c0", reference, powers, new_means,
                                 model, [])
    powers, _, _ = family_weights(
        updated.rows, updated.members, scan.tracks, confidence, "cross_rx_support",
        [int(following[sl].sum()) for sl in updated.slices],
    )
    # Select predictive-only entries at the existing point with the restored
    # curved mask and the same prior that the paired refit will consume.
    nomination = make_event_problem(scan, replacement, following, "c0", reference,
                                    powers, new_means, model, [])
    gates = conservative_recovery.retained_metrics(nomination, point)
    entries = select_entries(nomination, point, gates)
    info["linear"] = dict(offered_tracks=len(entries), offered_points=sum(e["points"] for e in entries),
                          accepted=False)
    proposal = dict(signed, node=replacement, keep=following, entries=entries, means=new_means,
                    powers=powers)
    if prefit is not None:
        selected, info["prefit"] = prefit(signed, proposal, half_width_km)
        if selected is None:
            return signed, info
        info["accepted"] = True
        info["linear"]["accepted"] = bool(selected["entries"])
        return selected, info
    pair = {arm: refit(scan, replacement, following, arm, powers, new_means, model, [], entries)
            for arm in algo08_collapsed.ARMS}
    info["phase_change_s"] = {arm: row["final_phase_change_s"] for arm, row in pair.items()}
    info["failed_tracks"] = {arm: sorted(t["component"] for t in r["gates"]["tracks"] + r["linear_gates"]
                                         if not t["compatible"]) for arm, r in pair.items()}
    info["accepted"] = pair_passes(pair, include_linear=bool(entries), half_width_km=half_width_km)
    proposal["arms"] = pair
    if not info["accepted"]:
        if repair is None:
            return signed, info
        proposal, info["repair"] = repair(proposal, half_width_km)
        if proposal is None:
            return signed, info
        info["accepted"] = True
    info["linear"]["accepted"] = bool(proposal["entries"])
    return proposal, info


def inference(record_curved, prepared, region, bound, stages, *, selected_evidence=None, repair=None,
              prefit=None):
    final, metadata = None, None

    def evidence(prepared, signed, fit):
        nonlocal final, metadata
        if fit is not None:
            raise ValueError("Salvage add-back requires the curved incumbent")
        if record_curved is not None:
            record_curved(signed)
        began = perf_counter()
        final, metadata = recover(signed, region.half_width_km, repair=repair, prefit=prefit)
        stages["single_salvage_and_predictive"] = perf_counter() - began
        if selected_evidence is not None:
            selected_evidence(prepared, final, None)

    result = algo08_collapsed.infer(prepared, region, bound, stages, selected_evidence=evidence)
    if final is not None:
        result["arms"] = {arm: dict(latlon=list(record["endpoint_latlon"]),
                                    rf_rms_hz=float(record["RMS_hz"]))
                          for arm, record in final["arms"].items()}
        result["metrics"]["salvage_addback"] = metadata
    return result


def binding(record_curved=None, *, repair=None, prefit=None):
    return patch.object(v5_core, "infer", partial(inference, record_curved, repair=repair, prefit=prefit))
