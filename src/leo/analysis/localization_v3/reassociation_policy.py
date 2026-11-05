"""Frozen paired RF/ownership acceptance for final satellite identity repair."""

import copy
import math

ARMS = ("c0", "fitted_c")
POLICY = "causal-reassociation-unique-receiver-groups-v1"


def select(baseline, records, guards):
    """Select only a qualified identity repair; geographic errors are opaque metadata."""
    eligible, review = [], []
    for row in records:
        name, reasons, guard = row["name"], [], guards.get(row["name"])
        if not row.get("accepted"):
            reasons.append("original_physical_acceptance_failed")
        if not guard or not guard.get("passed") or guard.get("model") != "receiver_offset":
            reasons.append("receiver_shared_competition_not_passed")
        elif (
            guard.get("unique_folds", 0) < 5
            or guard.get("missing")
            or not math.isfinite(guard.get("minimum_margin", float("nan")))
            or guard["minimum_margin"] <= 0
        ):
            reasons.append("incomplete_or_nonpositive_predictive_evidence")
        gains = row.get("gains", {})
        if any(
            not isinstance(gains.get(arm), (int, float))
            or not math.isfinite(gains[arm])
            or gains[arm] <= 0
            for arm in ARMS
        ):
            reasons.append("paired_RF_gain_failed")
        for arm in ARMS:
            fit = row.get("pair", {}).get(arm) or {}
            for key in (
                "qualified",
                "all_gates_pass",
                "phase_closed",
                "optimizer_success",
                "mixture_phase_interior",
            ):
                if fit.get(key) is not True:
                    reasons.append(arm + ":" + key)
            if fit.get("lost_ids_count", len(fit.get("lost_ids", []))) or fit.get(
                "unexpected_reassigned_ids_count", len(fit.get("unexpected_reassigned_ids", []))
            ):
                reasons.append(arm + ":native_ownership_violation")
            control = row.get("control", {}).get(arm) or {}
            if not fit.get("native_ids_sha256") or fit["native_ids_sha256"] != control.get(
                "native_ids_sha256"
            ):
                reasons.append(arm + ":native_evidence_not_matched")
        review.append(dict(name=name, eligible=not reasons, reasons=reasons))
        if not reasons:
            eligible.append(row)
    if not eligible:
        return dict(policy=POLICY, selected=None, final=copy.deepcopy(baseline), review=review)
    best = min(eligible, key=lambda row: (-sum(row["gains"][arm] for arm in ARMS), row["name"]))
    final = {
        arm: dict(
            x=best["pair"][arm]["x"],
            error_m=best["pair"][arm]["error_m"],
            objective=best["pair"][arm]["objective"],
            rms_hz=best["pair"][arm]["rms_hz"],
            associated=baseline[arm]["associated"],
        )
        for arm in ARMS
    }
    return dict(policy=POLICY, selected=best["name"], final=final, review=review)


def score_record(hypothesis, pair, control, bounds):
    complete = all(pair.get(arm) is not None and control.get(arm) is not None for arm in ARMS)
    gains = (
        {arm: bounds[arm] - pair[arm]["objective"] - hypothesis["penalty"] for arm in ARMS}
        if complete
        else {}
    )
    return dict(
        name=hypothesis["name"],
        hypothesis=hypothesis,
        pair=pair,
        control=control,
        gains=gains,
        accepted=bool(complete and all(value > 0 for value in gains.values())),
        bounds=bounds,
    )


def destination_owned(owners, new):
    return any(int(new) in set(map(int, owners[arm].values())) for arm in ARMS)


def fit_rows_complete(rows):
    expected = {(arm, start) for arm in ARMS for start in ("published", "family_omitted")}
    return (
        len(rows) == len(expected)
        and {(row.get("arm"), row.get("start")) for row in rows} == expected
        and all(row.get("status") == "complete" for row in rows)
    )


def propagation_eligible(receipt, bank_failures):
    failures = receipt["failures"]
    if not receipt["nominal_causality_verified"] or receipt["partial_or_unknown_blocks"]:
        return False
    if any(
        row["classification"] != "exclude_consistent_model_invalid_all_grid" for row in failures
    ):
        return False
    excluded = {int(row["norad"]) for row in failures}
    return len(excluded) == len(failures) and excluded == set(map(int, bank_failures))
