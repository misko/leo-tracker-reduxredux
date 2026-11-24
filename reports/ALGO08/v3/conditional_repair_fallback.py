"""Test a matched curvature-only refit when optional predictive support fails."""

from contextlib import contextmanager
from functools import partial
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3.history_policy import pair_passes

from blind_joint_finish import ARMS, arm_finish, elapsed, readout
from blind_joint_repair import failed_union


def eligible(candidate, region):
    arms = candidate["arms"]
    failed_curved, failed_predictive = failed_union(arms)
    return (bool(candidate["entries"] and failed_predictive) and not failed_curved
            and pair_passes(arms, half_width_km=region.half_width_km)
            and all(0 <= arms[arm]["final_phase_change_s"] <= .01 for arm in ARMS))


def conditional_fallback(candidate, region, measured):
    """Refit the same curved rows without any predictive entries in either arm."""
    original_reason = measured["repair"]["reason"]
    if not eligible(candidate, region):
        return None, original_reason

    trace = measured["conditional_repair_fallback"] = {"status": "rejected"}
    started = process_time(), perf_counter()
    scan, node, keep, powers, means, model = (candidate[key] for key in (
        "scan", "node", "keep", "powers", "means", "model"))
    entries = []
    try:
        arms = {}
        for arm in ARMS:
            seed = candidate["arms"][arm]
            arms[arm] = arm_finish(scan, node, keep, arm, seed["phase_reference"], powers, means,
                                   model, entries, seed["endpoint_east_north_km"])
        trace["finish"] = {arm: readout(record) for arm, record in arms.items()}
        complete = (pair_passes(arms, half_width_km=region.half_width_km)
                    and all(row["curved_points"] == int(keep.sum()) and not row["linear_points"]
                            and not row["failed_linear"] and 0 <= row["final_phase_change_s"] <= .01
                            and 0 <= row["phase_last_site_move_km"] <= .020
                            and np.isfinite(row["objective"]) and np.isfinite(row["rf_rms_hz"])
                            for row in trace["finish"].values()))
    except (AssertionError, ValueError, np.linalg.LinAlgError) as exc:
        trace["reason"] = f"{type(exc).__name__}: {exc}"
        return None, original_reason
    finally:
        trace["clocks"] = elapsed(*started)
    if not complete:
        trace["reason"] = "conditional_pair_gate"
        return None, original_reason
    trace["status"] = "qualified_for_standard_evidence"
    return dict(candidate, entries=entries, arms=arms), None


@contextmanager
def binding(reader, cutoff, audit, original_rank):
    import blind_joint_repair
    from nomination_handoff import routed_binding

    with (patch.object(blind_joint_repair, "repair_once", partial(
            blind_joint_repair.repair_once, conditional_fallback=conditional_fallback)),
          routed_binding(reader, cutoff, audit, original_rank)):
        yield
