"""Timing-only fragment preparation and independently qualified conditional fits."""

from leo.analysis.localization_v3.gap_fragments import gap_context
from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from leo.analysis.localization_v3.predictive_annotation import annotate
from leo.analysis.localization_v3.recovery_inclusion import audit_inclusion, fit_shared


def annotate_gap(context, inventory, source, branch_id, observations):
    d, target = gap_context(context, inventory, source, branch_id, observations)
    policy = NumericalPolicy(reference_limit_s=30, centered_lbfgsb=True)
    result = annotate(
        dict(d, numerical_policy=policy),
        inventory,
        branch_id,
        candidates=3,
        folds=3,
        target_record=target,
        shifted_origin=False,
    )
    result["gap_source"] = source
    return result, policy.receipt


def fit_gap(context, inventory, annotation, observations):
    policy = NumericalPolicy(reference_limit_s=30, centered_lbfgsb=True)
    d = dict(context, native_observations=observations, numerical_policy=policy)
    result = fit_shared(d, inventory, [annotation], conditional_satellite_refresh=True)
    return result, policy.receipt


def audit_gap(context, inventory, annotation, trial, observations):
    policy = NumericalPolicy(reference_limit_s=30, centered_lbfgsb=True)
    d = dict(context, native_observations=observations, numerical_policy=policy)
    return audit_inclusion(d, inventory, [annotation], trial, shared=True), policy.receipt
