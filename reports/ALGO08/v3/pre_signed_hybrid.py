"""Keep the actual named predictive roster and attempt the cumulative signed finish."""

from contextlib import contextmanager
from functools import wraps
from time import perf_counter
from unittest.mock import patch

import numpy as np

from causal_linear_refit import ARMS, elapsed, now


IDENTITY_CONFIDENCE = 0.95
GUARD_KM = 2.0
NUMERICAL_ERRORS = (AssertionError, ValueError, FloatingPointError, np.linalg.LinAlgError)


def interior_pair(arms, region):
    from leo.analysis.localization_v3.history_policy import pair_passes

    if set(arms) != set(ARMS) or not pair_passes(arms, include_linear=True, half_width_km=region.half_width_km):
        return False
    points = np.asarray([arms[arm]["endpoint_east_north_km"] for arm in ARMS])
    fit = np.asarray([[arms[arm][key] for key in ("RMS_hz", "negative_twice_elbo", "final_phase_change_s")]
                      for arm in ARMS])
    return bool(np.isfinite(fit).all() and np.max(abs(points)) <= region.half_width_km - GUARD_KM
                and np.linalg.norm(points[0] - points[1]) <= GUARD_KM)


def family_witnesses(tracks, node, keep, confidence, entries):
    """Index original history confidences by the same curved-row order."""
    sizes = {track["key"]: len(track["times"]) for track in tracks}
    rows = [row for row in node["seed"]["rows"] if row["active_curvature"]]
    evidence = {entry["candidate_index"]: None for entry in entries}
    offset = 0
    for row, strength in zip(rows, confidence, strict=True):
        width = sizes[row["component"]]
        selected = keep[offset:offset + width]
        offset += width
        if not np.any(selected):
            continue
        index = row["candidate_index"]
        best = evidence.setdefault(index, None)
        if np.all(selected) and np.isfinite(strength) and (best is None or strength > best):
            evidence[index] = float(strength)
    if offset != len(keep):
        raise ValueError("The named curved row order does not match the retained mask")
    return evidence


def eligible(scan, conservative, family, audit):
    if not family["linear_paired_valid"] or not family["linear_entries"]:
        return "no_admitted_predictive_pair"
    if not interior_pair(family["policy_arms"], scan.search_region):
        return "ordinary_pair_gate_or_region"
    try:
        strengths = family_witnesses(scan.tracks, conservative["final_node"], family["mask"],
                                     family["confidence"], family["linear_entries"])
    except (KeyError, ValueError) as exc:
        audit["unsupported_witness"] = str(exc)
        return "unrecognized_named_curved_layout"
    audit.update(families=len(strengths), family_confidence=sorted(
        ([int(scan.norads[index]), score] for index, score in strengths.items()), key=lambda row: row[0]))
    blind = sum(score is None or score < IDENTITY_CONFIDENCE for score in strengths.values())
    audit["families_without_strong_intact_witness"] = blind
    return "insufficient_family_witness" if blind or not strengths else None


def signed_refitter(original, ordinary, audit, warm=None):
    """Make one paired warm attempt, then serve the original pair on fallback."""
    candidate, cached = None, None
    order = []

    @wraps(original)
    def refit(scan, node, keep, arm, powers, means, model, events, entries):
        nonlocal candidate, cached
        shared = (scan, node, keep, powers, means, model, entries)
        expected = ARMS[len(order)] if len(order) < len(ARMS) else None
        if events or arm != expected:
            raise ValueError("Unexpected named signed refit structure")
        order.append(arm)
        if candidate is None:
            operation = warm
            if operation is None:
                from lighter_joint_estimator import warm_arm as operation

            candidate = dict(zip(("scan", "node", "keep", "powers", "means", "model", "entries"), shared, strict=True))
            candidate["arms"] = ordinary
            audit["attempted"] = True
            started = now()
            try:
                records, reasons = {}, {}
                for calibration in ARMS:
                    try:
                        record, reason = operation(candidate, means, calibration)
                    except NUMERICAL_ERRORS as exc:
                        record, reason = None, f"{type(exc).__name__}: {exc}"
                    if record is not None:
                        records[calibration] = record
                    reasons[calibration] = reason
                audit["arm_results"] = reasons
                if interior_pair(records, scan.search_region):
                    cached = records
            finally:
                audit["warm_attempt"] = elapsed(started)
            audit["warm_used"] = cached is not None
        elif any(candidate[key] is not value for key, value in
                 zip(("scan", "node", "keep", "powers", "means", "model", "entries"), shared, strict=True)):
            raise ValueError("Named signed fits did not retain identical paired inputs")
        if cached is not None:
            return cached[arm]
        started = now()
        try:
            return original(scan, node, keep, arm, powers, means, model, events, entries)
        finally:
            audit.setdefault("cold_arms", {})[arm] = elapsed(started)

    return refit


class SelectedIncumbent(Exception):
    def __init__(self, candidate, trial):
        super().__init__("Guarded causal incumbent")
        self.candidate = candidate
        self.trial = trial


@contextmanager
def binding(enabled, audit):
    from leo.analysis.localization_v3 import family_cavity, history_policy, signed_context
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    infer, history, signed = v5_core.infer, history_policy.history_policy, signed_context.signed_context
    nominate, cavity = family_cavity.nominate_families, family_cavity.cavity_policy

    @wraps(history)
    def timed_history(*values, **options):
        started = now()
        try:
            return history(*values, **options)
        finally:
            audit["named_history"].append(elapsed(started))

    @wraps(nominate)
    def timed_nomination(*values, **options):
        started = now()
        result = nominate(*values, **options)
        rows = result.get("families", ())
        audit["named_nominations"].append(dict(
            **elapsed(started), status=result["status"], families=len(rows),
            positive_offers=int(sum(row["best"] is not None and row["predictive_gain"] > 0 for row in rows)),
        ))
        return result

    @wraps(cavity)
    def timed_cavity(*values, **options):
        started = now()
        try:
            return cavity(*values, **options)
        finally:
            audit["named_cavity"].append(elapsed(started))

    def signed_for(finish_eligible, infer_start):
        @wraps(signed)
        def condition(scan, conservative, family, *values, **options):
            begun = perf_counter()
            started = now()
            trial = dict(use_hybrid=finish_eligible, original_infer_to_pre_signed=elapsed(infer_start))
            audit["signed"].append(trial)
            try:
                reason = eligible(scan, conservative, family, trial) if finish_eligible else "stock_control"
                trial["route"] = reason
                if reason is not None:
                    result = signed(scan, conservative, family, *values, **options)
                    trial["signed_qualified"] = bool(result["signed"]["selection"]["qualified"])
                    trial["signed_adopted"] = bool(result["signed"]["accepted"])
                    return result
                warm = trial["warm_signed"] = {}
                refit = signed_refitter(signed_context.refit, family["policy_arms"], warm)
                with patch.object(signed_context, "refit", refit):
                    result = signed(scan, conservative, family, *values, **options)
                trial["signed_qualified"] = bool(result["signed"]["selection"]["qualified"])
                trial["signed_adopted"] = bool(result["signed"]["accepted"])
                can_finish = (not trial["signed_qualified"] or (warm.get("warm_used") and trial["signed_adopted"]))
                if can_finish and interior_pair(result["arms"], scan.search_region):
                    trial.update(route="fixed_named_roster", original_alternatives_evaluated=False,
                                 signed_wall_s=perf_counter()-begun)
                    raise SelectedIncumbent(result, trial)
                trial["route"] = "fall_through_to_named_alternatives"
                if warm.get("warm_used"):
                    fallback_begin = now()
                    result = signed(scan, conservative, family, *values, **options)
                    trial["restore_named_signed"] = elapsed(fallback_begin)
                return result
            finally:
                trial["conditioning_total"] = elapsed(started)

        return condition

    @wraps(infer)
    def hybrid(prepared, region, bound, stages, *, selected_evidence=None, **options):
        infer_start = now()
        try:
            with patch.object(signed_context, "signed_context",
                              signed_for(enabled and selected_evidence is not None, infer_start)):
                return infer(prepared, region, bound, stages, selected_evidence=selected_evidence, **options)
        except SelectedIncumbent as selection:
            candidate, trial = selection.candidate, selection.trial

        build = algo08_position.selected_packet

        def full_packet(*args, **kwargs):
            packet = build(*args, **kwargs)
            if not packet["position_grid"]["complete"]:
                raise ValueError("The candidate numerical grid is incomplete")
            return packet

        started = now()
        try:
            with patch.object(algo08_position, "selected_packet", full_packet):
                selected_evidence(prepared, candidate, None)
        except NUMERICAL_ERRORS as exc:
            trial.update(route="retry_full_named_after_evidence", abandoned_evidence=elapsed(started),
                         reason=f"{type(exc).__name__}: {exc}", original_alternatives_evaluated=None)
            retry = now()
            try:
                return infer(prepared, region, bound, stages, selected_evidence=selected_evidence, **options)
            finally:
                trial["full_named_fallback"] = elapsed(retry)
        trial["standard_evidence"] = elapsed(started)
        stages["signed"] = trial["signed_wall_s"]
        return dict(
            status="ok", boundary=v5_core.BOUNDARY,
            arms={arm: dict(latlon=list(row["endpoint_latlon"]), rf_rms_hz=float(row["RMS_hz"]))
                  for arm, row in candidate["arms"].items()},
            metrics=dict(stage_s=stages, cavity_offered=None, original_alternatives_evaluated=False),
        )

    audit.update(named_history=[], signed=[], named_nominations=[], named_cavity=[])
    with (patch.object(history_policy, "history_policy", timed_history),
          patch.object(family_cavity, "nominate_families", timed_nomination),
          patch.object(family_cavity, "cavity_policy", timed_cavity),
          patch.object(v5_core, "infer", hybrid)):
        yield
