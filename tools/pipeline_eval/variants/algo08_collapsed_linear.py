"""One predictive-linear add-back from the unchanged collapsed curved incumbent."""

from functools import partial
from time import perf_counter
from unittest.mock import patch

from tools.pipeline_eval.variants import algo08_collapsed, v5_core


def admit(signed, half_width_km):
    from leo.analysis.localization_v3.event_position import make_event_problem, refit
    from leo.analysis.localization_v3.history_policy import paired_policy
    from leo.analysis.localization_v3.predictive_linear import select_entries

    original = signed["arms"]
    scan, node, keep = (signed[k] for k in ("scan", "node", "keep"))
    powers, means, model = (signed[k] for k in ("powers", "means", "model"))
    curved_c0 = original["c0"]
    problem = make_event_problem(scan, node, keep, "c0", curved_c0["phase_reference"],
                                 powers, means, model, [])
    entries = select_entries(problem, curved_c0["endpoint_east_north_km"], curved_c0["gates"])
    info = dict(offered_tracks=len(entries), offered_points=sum(e["points"] for e in entries),
                accepted=False)
    if not entries:
        return signed, info
    candidates = {arm: refit(scan, node, keep, arm, powers, means, model, [], entries)
                  for arm in algo08_collapsed.ARMS}
    selected, accepted = paired_policy(original, candidates, half_width_km=half_width_km)
    info.update(accepted=accepted, candidate={arm: dict(
        position=list(record["endpoint_latlon"]), phase_change_s=record["final_phase_change_s"],
        failed_tracks=sorted(t["component"] for t in record["gates"]["tracks"] + record["linear_gates"]
                             if not t["compatible"]),
    ) for arm, record in candidates.items()})
    if not accepted:
        return signed, info
    return dict(signed, entries=entries, arms=selected), info


def inference(record_curved, prepared, region, bound, stages, *, selected_evidence=None):
    final, metadata = None, None

    def evidence(prepared, signed, fit):
        nonlocal final, metadata
        if fit is not None:
            raise ValueError("Predictive add-back requires the curved incumbent")
        if record_curved is not None:
            record_curved(signed)
        began = perf_counter()
        final, metadata = admit(signed, region.half_width_km)
        stages["predictive_linear"] = perf_counter() - began
        if selected_evidence is not None:
            selected_evidence(prepared, final, None)

    result = algo08_collapsed.infer(prepared, region, bound, stages, selected_evidence=evidence)
    if final is not None:
        result["arms"] = {arm: dict(latlon=list(record["endpoint_latlon"]),
                                    rf_rms_hz=float(record["RMS_hz"]))
                          for arm, record in final["arms"].items()}
        result["metrics"]["predictive_linear"] = metadata
    return result


def binding(record_curved=None):
    return patch.object(v5_core, "infer", partial(inference, record_curved))
