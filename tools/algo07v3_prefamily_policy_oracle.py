# Frozen from 669611c5b:src/leo/analysis/localization_v3/history_policy.py.
# External serial scheduling oracle; never imported by the runtime.
"""Original family/history policy with paired predictive-linear acceptance."""

import copy

import numpy as np

from leo.analysis.localization_v3.conservative_recovery import retained_metrics
from leo.analysis.localization_v3.family_weighting import confidence_for, family_weights
from leo.analysis.localization_v3.history_position import (
    forecast_phase_mean,
    make_problem,
    problem,
    refit,
)
from leo.analysis.localization_v3.predictive_linear import refit as linear_refit
from leo.analysis.localization_v3.predictive_linear import select_entries
from leo.analysis.localization_v3.retained_position import phase_widths

ARMS = ("c0", "fitted_c")


def history_policy(scan, original, raw, forecast, *, case, cutoff_utc_ns, history_sha256):
    """Fit curved families and conditionally add predictive linear evidence.

    Region and history provenance enter explicitly. This produces the initial
    family-policy incumbent, not the later recovery/reassociation result.
    """
    common = dict(
        GPS_used=False,
        future_TLE_used=False,
        region_center=scan.search_region.center,
        box_width_km=scan.search_region.width_km,
        start_east_north_km=[0.0, 0.0],
        paired_c_masks_aliases_identities_and_budgets=True,
    )
    if original["status"] != "complete":
        return dict(common, status="failed", reason="initial_" + original["status"], policy_arms={})
    node = original["final_node"]
    original_keep = np.asarray(original["final_mask"], bool)
    p = problem(scan, node, "c0", original_keep)
    confidence = confidence_for(scan, node, original_keep, original)
    powers, owners, counts = family_weights(
        p.rows,
        p.members,
        scan.tracks,
        confidence,
        "cross_rx_support",
        [int(original_keep[sl].sum()) for sl in p.slices],
    )
    model, qualified = validate_history(
        raw,
        forecast,
        case=case,
        origin_utc_ns=scan.origin_utc_ns,
        cutoff_utc_ns=cutoff_utc_ns,
        raw_sha256=history_sha256,
    )
    _, receipts = phase_widths(scan, p.labels)
    means = forecast_phase_mean(receipts, model["shrinkage"])
    curved, keep, history = history_fit(scan, node, original_keep, powers, means, model)
    common.update(
        weights=powers,
        confidence=confidence,
        original_mask=original_keep,
        mask=keep,
        curved_gate_history=history,
        hyperparameters_from_pre_RF_TLE_only=model,
        earlier_TLE_validation_qualified=qualified,
        family_owners={str(int(scan.norads[j])): sorted(v) for j, v in owners.items()},
        family_points={str(int(scan.norads[j])): int(v) for j, v in counts.items()},
    )
    if (
        curved is None
        or not keep.any()
        or not pair_passes(curved, half_width_km=scan.search_region.half_width_km)
    ):
        return dict(
            common,
            status="failed",
            reason="no_qualified_curved_pair",
            curved_arms=curved,
            policy_arms={},
        )
    saved = curved["c0"]
    p = make_problem(
        scan,
        node,
        keep,
        "c0",
        np.asarray(saved["phase_reference"]),
        powers,
        means,
        model["multiplier"],
        model["nu"],
    )
    x = np.asarray(saved["endpoint_east_north_km"])
    entries = select_entries(p, x, retained_metrics(p, x))
    linear = {
        arm: linear_refit(scan, node, keep, powers, means, model, arm, entries) for arm in ARMS
    }
    policy, accepted = paired_policy(curved, linear, half_width_km=scan.search_region.half_width_km)
    return dict(
        common,
        status="accepted",
        policy_arms=policy,
        curved_arms=curved,
        linear_arms=linear,
        linear_entries=entries,
        linear_paired_valid=accepted,
        fallback=None if accepted else "curved_pair",
        linear_offered_tracks=len(entries),
        linear_offered_points=sum(e["points"] for e in entries),
        linear_used_points=sum(e["points"] for e in entries) if accepted else 0,
        no_IQ_reread=True,
        curved_only_calibration_no_linear_normal_equation_update=True,
        shared_full_calibration_covariance_preserved=True,
        per_new_curve_constant_sigma_hz=300.0,
        unseen_noise_inverse_precision_mean=2.0,
        phase_rounds=5,
        steps_per_round=48,
        maximum_curved_gate_rounds=4,
        no_stationary_history_position_pooling=True,
    )


def validate_history(raw, forecast, *, case, origin_utc_ns, cutoff_utc_ns, raw_sha256):
    """Check every historical candidate, including candidates not RF selected."""
    if not forecast.get("strictly_pre_RF") or forecast.get("GPS_or_radio_used") is not False:
        raise ValueError("phase prior is not certified pre-RF")
    if raw["case"] != case or forecast["case"] != case:
        raise ValueError("causal history belongs to another recording")
    if forecast["history_sha256"] != raw_sha256:
        raise ValueError("causal history digest changed")
    if any(
        raw[name] != dict(origin_utc_ns=origin_utc_ns, cutoff_utc_ns=cutoff_utc_ns)[name]
        for name in ("origin_utc_ns", "cutoff_utc_ns")
    ):
        raise ValueError("causal history timing belongs to another scan")
    cutoff = raw["cutoff_utc_ns"]
    for versions in raw["past_versions"].values():
        for version in versions:
            if version["epoch"] > cutoff or version["collected_utc_ns"] > cutoff:
                raise ValueError("post-scan element in causal history")
    valid = forecast["distribution_validation"]
    original = forecast["original_distribution_validation"]
    qualified = (
        valid["count"] >= 30
        and valid["negative_twice_log_density"] < original["negative_twice_log_density"]
    )
    model = (
        copy.deepcopy(forecast["all_past_distribution"])
        if qualified
        else dict(shrinkage=0.0, multiplier=1.0, nu=None, fallback=True)
    )
    if (
        not 0 <= model["shrinkage"] <= 1
        or not np.isfinite(model["multiplier"])
        or model["multiplier"] <= 0
    ):
        raise ValueError("invalid historical phase distribution")
    return model, bool(qualified)


def pair_passes(pair, include_linear=False, *, half_width_km=12.5):
    """The same observations/hypothesis must qualify in both c arms."""
    for arm in ARMS:
        record = pair[arm]
        tracks = record["gates"]["tracks"] + (
            record.get("linear_gates", []) if include_linear else []
        )
        if not tracks or not all(t["compatible"] for t in tracks):
            return False
        if include_linear and record["final_phase_change_s"] > 0.01:
            return False
        x = np.asarray(record["endpoint_east_north_km"])
        if x.shape != (2,) or not np.isfinite(x).all() or np.any(abs(x) > half_width_km + 1e-8):
            return False
    return True


def paired_policy(curved, linear, *, half_width_km=12.5):
    """Never choose one c arm using the other arm's data or evaluation error."""
    accepted = pair_passes(linear, include_linear=True, half_width_km=half_width_km)
    return (linear if accepted else curved), accepted


def history_fit(scan, node, original_keep, powers, means, model):

    base = problem(scan, node, "c0", original_keep)
    keep = np.array(original_keep, bool, copy=True)
    steps = []
    pair = None
    for epoch in range(4):
        if not keep.any():
            break
        pair = {
            arm: refit(scan, node, keep, arm, powers, means, model["multiplier"], model["nu"])
            for arm in ARMS
        }
        failed = {
            r["component"]
            for arm in ARMS
            for r in pair[arm]["gates"]["tracks"]
            if not r["compatible"]
        }
        steps.append(dict(epoch=epoch, input_points=int(keep.sum()), failed=sorted(failed)))
        if not failed or epoch == 3:
            break
        for row, sl in zip(base.rows, base.slices, strict=True):
            if row["component"] in failed:
                keep[sl] = False
    return pair, keep, steps
