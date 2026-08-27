"""Retrospective discrete smoothing over a completed causal multi-dwell filter.

The forward filter preserves complete assignment histories in every retained
mode.  This analyzer therefore obtains exact fixed-interval identity marginals
within that retained family by summing the final path probabilities.  It never
re-scores response, refits nuisance state, or rewrites the causal rolling
receipts.  Future dwells are intentionally allowed to revise earlier identity
probabilities, so this output is retrospective and cannot be presented as an
online prediction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from leo.analysis.multi_dwell_catalogue_smoothing import (
    CatalogueIdentity,
    MultiDwellCatalogueFilterResult,
    MultiDwellModeScore,
    RollingDwellAssociation,
)
from leo.contracts.digests import Sha256Digest, canonical_digest

_ALGORITHM_VERSION: Literal["retained-history-fixed-interval-identity-smoother-v1"] = (
    "retained-history-fixed-interval-identity-smoother-v1"
)
_TIE_ULPS = 8.0


class MultiDwellBackwardSmoothingInputError(ValueError):
    """The forward result is stale or internally inconsistent."""


class MultiDwellBackwardSmoothingNumericalError(ValueError):
    """The retained posterior cannot be normalized reliably."""


@dataclass(frozen=True, slots=True)
class IdentityPosteriorProbability:
    identity: CatalogueIdentity
    posterior_probability: float

    def __post_init__(self) -> None:
        if self.identity is not None and (
            isinstance(self.identity, bool)
            or not isinstance(self.identity, int)
            or self.identity <= 0
        ):
            raise MultiDwellBackwardSmoothingInputError(
                "smoothed identity must be NULL or a positive catalogue number"
            )
        if not math.isfinite(self.posterior_probability) or not (
            0.0 <= self.posterior_probability <= 1.0
        ):
            raise MultiDwellBackwardSmoothingNumericalError(
                "smoothed identity probability is invalid"
            )


@dataclass(frozen=True, slots=True)
class SmoothedDwellIdentityPosterior:
    dwell_index: int
    dwell_id: str
    forward_identity_posterior: tuple[IdentityPosteriorProbability, ...]
    smoothed_identity_posterior: tuple[IdentityPosteriorProbability, ...]
    forward_nearest_identity: CatalogueIdentity
    smoothed_nearest_identity: CatalogueIdentity
    smoothed_ambiguity_set: tuple[CatalogueIdentity, ...]
    total_variation_revision: float
    exact_smoothed_tie: bool

    def __post_init__(self) -> None:
        if self.dwell_index < 0 or not self.dwell_id:
            raise MultiDwellBackwardSmoothingInputError("smoothed dwell identity is invalid")
        _validate_identity_distribution(self.forward_identity_posterior)
        _validate_identity_distribution(self.smoothed_identity_posterior)
        if not math.isfinite(self.total_variation_revision) or not (
            0.0 <= self.total_variation_revision <= 1.0
        ):
            raise MultiDwellBackwardSmoothingNumericalError(
                "smoothed total-variation revision is invalid"
            )
        smoothed = dict(
            (item.identity, item.posterior_probability) for item in self.smoothed_identity_posterior
        )
        forward = dict(
            (item.identity, item.posterior_probability) for item in self.forward_identity_posterior
        )
        forward_maximum = max(forward.values())
        expected_forward_nearest = next(
            identity
            for identity in _ordered_identities(tuple(forward))
            if _scores_tied(forward[identity], forward_maximum)
        )
        if self.forward_nearest_identity != expected_forward_nearest:
            raise MultiDwellBackwardSmoothingInputError(
                "forward nearest identity does not match its posterior"
            )
        maximum = max(smoothed.values())
        expected_ambiguity = tuple(
            identity
            for identity in _ordered_identities(tuple(smoothed))
            if _scores_tied(smoothed[identity], maximum)
        )
        if self.smoothed_ambiguity_set != expected_ambiguity:
            raise MultiDwellBackwardSmoothingInputError(
                "smoothed ambiguity set does not match the posterior"
            )
        if self.exact_smoothed_tie != (len(expected_ambiguity) > 1):
            raise MultiDwellBackwardSmoothingInputError("smoothed tie diagnostic is inconsistent")
        if self.smoothed_nearest_identity != expected_ambiguity[0]:
            raise MultiDwellBackwardSmoothingInputError(
                "smoothed nearest identity is not canonical"
            )
        expected_revision = 0.5 * math.fsum(
            abs(smoothed[identity] - forward[identity]) for identity in forward
        )
        if not math.isclose(
            self.total_variation_revision,
            expected_revision,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise MultiDwellBackwardSmoothingInputError(
                "smoothed total-variation revision is inconsistent"
            )


@dataclass(frozen=True, slots=True)
class MultiDwellFixedIntervalIdentitySmoothingResult:
    source_filter_algorithm_version: str
    source_result_digest: Sha256Digest
    dwell_ids: tuple[str, ...]
    smoothed_dwells: tuple[SmoothedDwellIdentityPosterior, ...]
    any_input_pruning: bool
    abstention_recommended: bool
    abstention_diagnostics: tuple[str, ...]
    algorithm_version: Literal["retained-history-fixed-interval-identity-smoother-v1"] = field(
        default=_ALGORITHM_VERSION, init=False
    )
    final_retained_histories_consumed: Literal[True] = field(default=True, init=False)
    response_rescored: Literal[False] = field(default=False, init=False)
    nuisance_states_refit_or_smoothed: Literal[False] = field(default=False, init=False)
    future_response_used_for_retrospective_identity_smoothing: Literal[True] = field(
        default=True, init=False
    )
    forward_receipts_mutated: Literal[False] = field(default=False, init=False)
    posterior_conditioned_on_retained_beam: Literal[True] = field(default=True, init=False)
    fixed_interval_not_online: Literal[True] = field(default=True, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)
    content_digest: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if not self.dwell_ids or len(self.dwell_ids) != len(self.smoothed_dwells):
            raise MultiDwellBackwardSmoothingInputError(
                "smoothed result must cover every source dwell"
            )
        if tuple(item.dwell_id for item in self.smoothed_dwells) != self.dwell_ids or tuple(
            item.dwell_index for item in self.smoothed_dwells
        ) != tuple(range(len(self.dwell_ids))):
            raise MultiDwellBackwardSmoothingInputError("smoothed dwell inventory is not canonical")
        if self.abstention_diagnostics != tuple(sorted(set(self.abstention_diagnostics))):
            raise MultiDwellBackwardSmoothingInputError(
                "smoothing abstention diagnostics must be unique and ordered"
            )
        if self.abstention_recommended != bool(self.abstention_diagnostics):
            raise MultiDwellBackwardSmoothingInputError(
                "smoothing abstention flag does not match diagnostics"
            )
        object.__setattr__(self, "content_digest", canonical_digest(self._digest_payload()))

    def _digest_payload(self) -> dict[str, object]:
        return {
            "source_filter_algorithm_version": self.source_filter_algorithm_version,
            "source_result_digest": self.source_result_digest,
            "dwell_ids": self.dwell_ids,
            "smoothed_dwells": tuple(
                {
                    "dwell_index": item.dwell_index,
                    "dwell_id": item.dwell_id,
                    "forward": tuple(
                        (entry.identity, entry.posterior_probability)
                        for entry in item.forward_identity_posterior
                    ),
                    "smoothed": tuple(
                        (entry.identity, entry.posterior_probability)
                        for entry in item.smoothed_identity_posterior
                    ),
                    "forward_nearest_identity": item.forward_nearest_identity,
                    "smoothed_nearest_identity": item.smoothed_nearest_identity,
                    "smoothed_ambiguity_set": item.smoothed_ambiguity_set,
                    "total_variation_revision": item.total_variation_revision,
                    "exact_smoothed_tie": item.exact_smoothed_tie,
                }
                for item in self.smoothed_dwells
            ),
            "any_input_pruning": self.any_input_pruning,
            "abstention_recommended": self.abstention_recommended,
            "abstention_diagnostics": self.abstention_diagnostics,
            "algorithm_version": self.algorithm_version,
            "final_retained_histories_consumed": self.final_retained_histories_consumed,
            "response_rescored": self.response_rescored,
            "nuisance_states_refit_or_smoothed": self.nuisance_states_refit_or_smoothed,
            "future_response_used_for_retrospective_identity_smoothing": (
                self.future_response_used_for_retrospective_identity_smoothing
            ),
            "forward_receipts_mutated": self.forward_receipts_mutated,
            "posterior_conditioned_on_retained_beam": (self.posterior_conditioned_on_retained_beam),
            "fixed_interval_not_online": self.fixed_interval_not_online,
            "identity_claimed": self.identity_claimed,
        }


def smooth_multi_dwell_catalogue_identities(
    result: MultiDwellCatalogueFilterResult,
) -> MultiDwellFixedIntervalIdentitySmoothingResult:
    """Marginalize final retained histories into earlier identity posteriors."""

    _validate_forward_result(result)
    source_digest = canonical_digest(_forward_result_payload(result))
    identity_inventory: tuple[CatalogueIdentity, ...] = (None, *result.catalog_numbers)
    smoothed_dwells = []
    for dwell_index, rolling in enumerate(result.rolling):
        forward = _identity_distribution(
            modes=rolling.modes,
            assignment_index=dwell_index,
            identity_inventory=identity_inventory,
        )
        smoothed = _identity_distribution(
            modes=result.final_modes,
            assignment_index=dwell_index,
            identity_inventory=identity_inventory,
        )
        smoothed_probabilities = {item.identity: item.posterior_probability for item in smoothed}
        maximum = max(smoothed_probabilities.values())
        ambiguity = tuple(
            identity
            for identity in identity_inventory
            if _scores_tied(smoothed_probabilities[identity], maximum)
        )
        forward_probabilities = {item.identity: item.posterior_probability for item in forward}
        total_variation = 0.5 * math.fsum(
            abs(smoothed_probabilities[identity] - forward_probabilities[identity])
            for identity in identity_inventory
        )
        smoothed_dwells.append(
            SmoothedDwellIdentityPosterior(
                dwell_index=dwell_index,
                dwell_id=rolling.dwell_id,
                forward_identity_posterior=forward,
                smoothed_identity_posterior=smoothed,
                forward_nearest_identity=rolling.nearest_identity,
                smoothed_nearest_identity=ambiguity[0],
                smoothed_ambiguity_set=ambiguity,
                total_variation_revision=min(1.0, max(0.0, total_variation)),
                exact_smoothed_tie=len(ambiguity) > 1,
            )
        )
    diagnostics = set()
    if result.any_pruning:
        diagnostics.add("input-beam-pruned")
    if any(item.exact_smoothed_tie for item in smoothed_dwells):
        diagnostics.add("smoothed-exact-tie")
    if smoothed_dwells[-1].smoothed_nearest_identity is None:
        diagnostics.add("smoothed-final-null-nearest")
    return MultiDwellFixedIntervalIdentitySmoothingResult(
        source_filter_algorithm_version=result.algorithm_version,
        source_result_digest=source_digest,
        dwell_ids=result.dwell_ids,
        smoothed_dwells=tuple(smoothed_dwells),
        any_input_pruning=result.any_pruning,
        abstention_recommended=bool(diagnostics),
        abstention_diagnostics=tuple(sorted(diagnostics)),
    )


def _identity_distribution(
    *,
    modes: tuple[MultiDwellModeScore, ...],
    assignment_index: int,
    identity_inventory: tuple[CatalogueIdentity, ...],
) -> tuple[IdentityPosteriorProbability, ...]:
    values = {identity: 0.0 for identity in identity_inventory}
    for mode in modes:
        identity = mode.assignments[assignment_index]
        values[identity] += mode.posterior_probability_within_retained_beam
    total = math.fsum(values.values())
    if not math.isfinite(total) or total <= 0.0:
        raise MultiDwellBackwardSmoothingNumericalError(
            "identity marginal has no representable posterior mass"
        )
    probabilities = {identity: value / total for identity, value in values.items()}
    correction = 1.0 - math.fsum(probabilities.values())
    maximum_identity = max(identity_inventory, key=lambda identity: probabilities[identity])
    probabilities[maximum_identity] += correction
    return tuple(
        IdentityPosteriorProbability(
            identity=identity,
            posterior_probability=probabilities[identity],
        )
        for identity in identity_inventory
    )


def _validate_forward_result(result: MultiDwellCatalogueFilterResult) -> None:
    if result.algorithm_version != "causal-rb-multi-dwell-filter-v1":
        raise MultiDwellBackwardSmoothingInputError("forward algorithm identity is stale")
    if (
        result.tau_policy != "fixed-precomputed-v1"
        or result.fixed_lag_backward_smoothing_performed
        or result.ecm_performed
        or not result.candidate_only
        or result.identity_claimed
        or not result.response_free_prediction_bank_required
        or result.emitter_model != "one-source-state-per-dwell-k02-distinct-history-v1"
        or result.simultaneous_two_emitter_modelled
        or result.nuisance_scope != "receiver-local-nontransferable-v1"
        or result.nuisance_transferable_to_satellite_frequency_state_v1
    ):
        raise MultiDwellBackwardSmoothingInputError(
            "forward filter claim or nuisance boundary is stale"
        )
    if not result.dwell_ids or result.dwell_ids != tuple(item.dwell_id for item in result.rolling):
        raise MultiDwellBackwardSmoothingInputError("forward dwell inventory is inconsistent")
    if result.catalog_numbers != tuple(sorted(set(result.catalog_numbers))):
        raise MultiDwellBackwardSmoothingInputError("forward catalogue inventory is not canonical")
    if result.final_modes != result.rolling[-1].modes:
        raise MultiDwellBackwardSmoothingInputError(
            "forward final histories do not match the last rolling receipt"
        )
    if result.evaluated_extension_count != sum(
        item.evaluated_extension_count for item in result.rolling
    ) or result.evaluated_support_row_count != sum(
        item.evaluated_support_row_count for item in result.rolling
    ):
        raise MultiDwellBackwardSmoothingInputError("forward work accounting is inconsistent")
    for dwell_index, rolling in enumerate(result.rolling):
        if rolling.dwell_index != dwell_index or rolling.dwell_id != result.dwell_ids[dwell_index]:
            raise MultiDwellBackwardSmoothingInputError(
                "forward rolling chronology is inconsistent"
            )
        if (
            not rolling.score_before_assimilation
            or rolling.later_response_used_for_current_score_or_assimilation
            or not rolling.whole_input_envelope_validated_before_filtering
            or not rolling.posterior_conditioned_on_retained_beam
        ):
            raise MultiDwellBackwardSmoothingInputError(
                "forward rolling causality boundary is stale"
            )
        _validate_mode_family(
            rolling=rolling,
            expected_assignment_count=dwell_index + 1,
            catalog_numbers=result.catalog_numbers,
        )
        if rolling.nearest_identity != rolling.modes[0].current_identity:
            raise MultiDwellBackwardSmoothingInputError(
                "forward nearest identity disagrees with rank one"
            )
    if result.any_pruning != any(item.current_step_beam_pruned for item in result.rolling):
        raise MultiDwellBackwardSmoothingInputError("forward pruning accounting is inconsistent")
    if result.final_abstention_recommended != bool(result.final_abstention_diagnostics):
        raise MultiDwellBackwardSmoothingInputError("forward abstention accounting is stale")


def _validate_mode_family(
    *,
    rolling: RollingDwellAssociation,
    expected_assignment_count: int,
    catalog_numbers: tuple[int, ...],
) -> None:
    modes = rolling.modes
    if not modes or tuple(item.rank for item in modes) != tuple(range(1, len(modes) + 1)):
        raise MultiDwellBackwardSmoothingInputError("forward mode ranks are not canonical")
    if tuple(item.cumulative_negative_log_joint for item in modes) != tuple(
        sorted(item.cumulative_negative_log_joint for item in modes)
    ):
        raise MultiDwellBackwardSmoothingInputError("forward modes are not score ordered")
    probabilities = tuple(item.posterior_probability_within_retained_beam for item in modes)
    if any(not math.isfinite(item) or item < 0.0 for item in probabilities) or not math.isclose(
        math.fsum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12
    ):
        raise MultiDwellBackwardSmoothingNumericalError(
            "forward retained-mode probabilities are not normalized"
        )
    minimum_score = modes[0].cumulative_negative_log_joint
    weights = tuple(
        math.exp(-(item.cumulative_negative_log_joint - minimum_score)) for item in modes
    )
    weight_sum = math.fsum(weights)
    expected_probabilities = tuple(item / weight_sum for item in weights)
    if any(
        not math.isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-15)
        for observed, expected in zip(probabilities, expected_probabilities, strict=True)
    ):
        raise MultiDwellBackwardSmoothingInputError(
            "forward posterior probabilities disagree with path scores"
        )
    for mode in modes:
        if len(mode.assignments) != expected_assignment_count or any(
            item is not None and item not in catalog_numbers for item in mode.assignments
        ):
            raise MultiDwellBackwardSmoothingInputError(
                "forward mode assignment inventory is invalid"
            )
        active = tuple(sorted({item for item in mode.assignments if item is not None}))
        if mode.active_catalog_numbers != active or mode.current_identity != mode.assignments[-1]:
            raise MultiDwellBackwardSmoothingInputError(
                "forward active-catalogue accounting is inconsistent"
            )
        numeric_values = (
            mode.transition_negative_log_probability,
            mode.next_dwell_predictive_negative_log_likelihood,
            mode.cumulative_negative_log_joint,
            mode.nuisance.predicted_drift_mean_hz_per_s,
            mode.nuisance.predicted_drift_standard_uncertainty_hz_per_s,
            mode.nuisance.filtered_drift_mean_hz_per_s,
            mode.nuisance.filtered_drift_standard_uncertainty_hz_per_s,
            mode.nuisance.dwell_offset_mean_hz,
            mode.nuisance.dwell_offset_standard_uncertainty_hz,
            mode.nuisance.drift_offset_covariance_hz2_per_s,
        )
        if any(not math.isfinite(item) for item in numeric_values):
            raise MultiDwellBackwardSmoothingNumericalError(
                "forward score or nuisance state is not finite"
            )
        if (
            mode.transition_negative_log_probability < 0.0
            or mode.nuisance.predicted_drift_standard_uncertainty_hz_per_s <= 0.0
            or mode.nuisance.filtered_drift_standard_uncertainty_hz_per_s <= 0.0
            or mode.nuisance.dwell_offset_standard_uncertainty_hz <= 0.0
        ):
            raise MultiDwellBackwardSmoothingInputError(
                "forward probability or nuisance scale is invalid"
            )


def _validate_identity_distribution(
    values: tuple[IdentityPosteriorProbability, ...],
) -> None:
    identities = tuple(item.identity for item in values)
    if identities != _ordered_identities(identities):
        raise MultiDwellBackwardSmoothingInputError(
            "identity posterior inventory must be unique and canonical"
        )
    if not math.isclose(
        math.fsum(item.posterior_probability for item in values),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise MultiDwellBackwardSmoothingNumericalError(
            "identity posterior probabilities do not sum to one"
        )


def _ordered_identities(values: tuple[CatalogueIdentity, ...]) -> tuple[CatalogueIdentity, ...]:
    if len(set(values)) != len(values):
        raise MultiDwellBackwardSmoothingInputError("identity inventory contains duplicates")
    return tuple(sorted(values, key=lambda item: (item is not None, -1 if item is None else item)))


def _scores_tied(left: float, right: float) -> bool:
    tolerance = _TIE_ULPS * math.ulp(max(1.0, abs(left), abs(right)))
    return abs(left - right) <= tolerance


def _forward_result_payload(result: MultiDwellCatalogueFilterResult) -> dict[str, object]:
    return {
        "dwell_ids": result.dwell_ids,
        "catalog_numbers": result.catalog_numbers,
        "rolling": tuple(
            {
                "dwell_index": item.dwell_index,
                "dwell_id": item.dwell_id,
                "modes": tuple(_mode_payload(mode) for mode in item.modes),
                "mixture_predictive_negative_log_likelihood": (
                    item.mixture_predictive_negative_log_likelihood
                ),
                "current_step_beam_pruned": item.current_step_beam_pruned,
                "prior_or_current_beam_pruned": item.prior_or_current_beam_pruned,
            }
            for item in result.rolling
        ),
        "evaluated_extension_count": result.evaluated_extension_count,
        "evaluated_support_row_count": result.evaluated_support_row_count,
        "any_pruning": result.any_pruning,
        "final_abstention_recommended": result.final_abstention_recommended,
        "final_abstention_diagnostics": result.final_abstention_diagnostics,
        "algorithm_version": result.algorithm_version,
        "nuisance_model": result.nuisance_model,
        "tau_policy": result.tau_policy,
        "emitter_model": result.emitter_model,
    }


def _mode_payload(mode: MultiDwellModeScore) -> dict[str, object]:
    return {
        "rank": mode.rank,
        "assignments": mode.assignments,
        "active_catalog_numbers": mode.active_catalog_numbers,
        "transition_negative_log_probability": mode.transition_negative_log_probability,
        "next_dwell_predictive_negative_log_likelihood": (
            mode.next_dwell_predictive_negative_log_likelihood
        ),
        "cumulative_negative_log_joint": mode.cumulative_negative_log_joint,
        "posterior_probability_within_retained_beam": (
            mode.posterior_probability_within_retained_beam
        ),
        "nuisance": {
            "dwell_id": mode.nuisance.dwell_id,
            "hardware_epoch_id": mode.nuisance.hardware_epoch_id,
            "reset_reason": mode.nuisance.reset_reason,
            "predicted_drift_mean_hz_per_s": mode.nuisance.predicted_drift_mean_hz_per_s,
            "predicted_drift_standard_uncertainty_hz_per_s": (
                mode.nuisance.predicted_drift_standard_uncertainty_hz_per_s
            ),
            "filtered_drift_mean_hz_per_s": mode.nuisance.filtered_drift_mean_hz_per_s,
            "filtered_drift_standard_uncertainty_hz_per_s": (
                mode.nuisance.filtered_drift_standard_uncertainty_hz_per_s
            ),
            "dwell_offset_mean_hz": mode.nuisance.dwell_offset_mean_hz,
            "dwell_offset_standard_uncertainty_hz": (
                mode.nuisance.dwell_offset_standard_uncertainty_hz
            ),
            "drift_offset_covariance_hz2_per_s": (mode.nuisance.drift_offset_covariance_hz2_per_s),
        },
    }
