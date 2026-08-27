"""Persisted posterior over sequential multi-dwell catalogue histories."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier
from leo.contracts.standard_pipeline import StandardScientificStatus


class MultiDwellHistoryAssignmentV1(ContractModel):
    schema_version: Literal[1] = 1
    dwell_id: Identifier
    catalog_number: Annotated[int | None, Field(gt=0)]


class MultiDwellHistoryModeV1(ContractModel):
    schema_version: Literal[1] = 1
    rank: Annotated[int, Field(gt=0)]
    assignments: Annotated[tuple[MultiDwellHistoryAssignmentV1, ...], Field(min_length=1)]
    active_catalog_numbers: Annotated[tuple[int, ...], Field(max_length=2)]
    cumulative_negative_log_joint: float
    log_posterior_probability: Annotated[float, Field(le=0.0)]
    posterior_probability: Annotated[float, Field(gt=0.0, le=1.0)]
    handoff_count: Annotated[int, Field(ge=0)]
    null_dwell_count: Annotated[int, Field(ge=0)]
    mode_digest: Sha256Digest

    @model_validator(mode="after")
    def _mode_is_closed(self) -> Self:
        numeric = (
            self.cumulative_negative_log_joint,
            self.log_posterior_probability,
            self.posterior_probability,
        )
        if any(not math.isfinite(item) for item in numeric):
            raise ValueError("multi-dwell mode score must be finite")
        dwell_ids = tuple(item.dwell_id for item in self.assignments)
        if len(set(dwell_ids)) != len(dwell_ids):
            raise ValueError("multi-dwell mode repeats a dwell")
        assigned = tuple(
            sorted(
                {
                    item.catalog_number
                    for item in self.assignments
                    if item.catalog_number is not None
                }
            )
        )
        if self.active_catalog_numbers != assigned:
            raise ValueError("multi-dwell active catalogue inventory is inconsistent")
        expected_handoffs = sum(
            left.catalog_number != right.catalog_number
            for left, right in zip(self.assignments, self.assignments[1:], strict=False)
        )
        if self.handoff_count != expected_handoffs:
            raise ValueError("multi-dwell handoff count is inconsistent")
        if self.null_dwell_count != sum(item.catalog_number is None for item in self.assignments):
            raise ValueError("multi-dwell NULL count is inconsistent")
        if not math.isclose(
            self.posterior_probability,
            math.exp(self.log_posterior_probability),
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise ValueError("multi-dwell mode probability disagrees with log posterior")
        if self.mode_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"mode_digest"})
        ):
            raise ValueError("multi-dwell mode digest does not match content")
        return self


class DwellCatalogueProbabilityV1(ContractModel):
    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(gt=0)]
    posterior_probability: Annotated[float, Field(ge=0.0, le=1.0)]


class MultiDwellIdentityPosteriorV1(ContractModel):
    schema_version: Literal[1] = 1
    dwell_index: Annotated[int, Field(ge=0)]
    dwell_id: Identifier
    unassigned_probability: Annotated[float, Field(ge=0.0, le=1.0)]
    catalogue_probabilities: tuple[DwellCatalogueProbabilityV1, ...]
    exact_tie: bool

    @model_validator(mode="after")
    def _posterior_is_closed(self) -> Self:
        probabilities = (self.unassigned_probability,) + tuple(
            item.posterior_probability for item in self.catalogue_probabilities
        )
        if any(not math.isfinite(item) for item in probabilities):
            raise ValueError("multi-dwell identity probabilities must be finite")
        numbers = tuple(item.catalog_number for item in self.catalogue_probabilities)
        if numbers != tuple(sorted(set(numbers))):
            raise ValueError("multi-dwell identity catalogue inventory is not canonical")
        if not math.isclose(math.fsum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("multi-dwell identity posterior must sum to one")
        ordered_probabilities = (self.unassigned_probability,) + tuple(
            item.posterior_probability for item in self.catalogue_probabilities
        )
        maximum = max(ordered_probabilities)
        tied = sum(
            abs(item - maximum) <= 8.0 * math.ulp(max(1.0, abs(item), abs(maximum)))
            for item in ordered_probabilities
        )
        if self.exact_tie != (tied > 1):
            raise ValueError("multi-dwell identity tie flag is inconsistent")
        return self


class MultiDwellCataloguePosteriorV1(ContractModel):
    """Durable candidate-only posterior produced from a bounded forward filter."""

    schema_version: Literal[1] = 1
    kind: Literal["multi-dwell-catalogue-posterior"] = "multi-dwell-catalogue-posterior"
    algorithm_version: Literal["causal-filter-plus-fixed-interval-identity-v1"] = (
        "causal-filter-plus-fixed-interval-identity-v1"
    )
    source_filter_algorithm_version: Literal["causal-rb-multi-dwell-filter-v1"]
    source_filter_result_digest: Sha256Digest
    source_evidence_digest: Sha256Digest
    response_free_prediction_bank_digest: Sha256Digest
    filter_config_digest: Sha256Digest
    smoothing_result_digest: Sha256Digest
    dwell_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=4096)]
    catalog_numbers: Annotated[tuple[int, ...], Field(min_length=1, max_length=4096)]
    source_retained_mode_count: Annotated[int, Field(gt=0)]
    reported_positive_mode_count: Annotated[int, Field(gt=0)]
    zero_probability_mode_count: Annotated[int, Field(ge=0)]
    modes: Annotated[tuple[MultiDwellHistoryModeV1, ...], Field(min_length=1, max_length=4096)]
    smoothed_identity_posteriors: Annotated[
        tuple[MultiDwellIdentityPosteriorV1, ...], Field(min_length=1, max_length=4096)
    ]
    any_beam_pruning: bool
    retained_history_family_complete: bool
    status: Literal[StandardScientificStatus.PARTIAL] = StandardScientificStatus.PARTIAL
    posterior_conditioned_on_retained_beam: Literal[True] = True
    future_response_used_for_retrospective_identity_smoothing: Literal[True] = True
    forward_scores_recomputed_during_persistence: Literal[False] = False
    receiver_local_nuisance_excluded: Literal[True] = True
    nuisance_transferable_to_satellite_state: Literal[False] = False
    one_source_state_per_dwell: Literal[True] = True
    simultaneous_two_emitter_modelled: Literal[False] = False
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False
    navigation_fix_claimed: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _posterior_is_closed(self) -> Self:
        if self.dwell_ids != tuple(dict.fromkeys(self.dwell_ids)):
            raise ValueError("multi-dwell posterior dwell inventory must be unique and ordered")
        if self.catalog_numbers != tuple(sorted(set(self.catalog_numbers))):
            raise ValueError("multi-dwell posterior catalogue inventory is not canonical")
        if (
            self.reported_positive_mode_count + self.zero_probability_mode_count
            != self.source_retained_mode_count
            or self.reported_positive_mode_count != len(self.modes)
        ):
            raise ValueError("multi-dwell posterior mode accounting is inconsistent")
        if tuple(item.rank for item in self.modes) != tuple(range(1, len(self.modes) + 1)):
            raise ValueError("multi-dwell posterior ranks must be contiguous")
        if len({item.mode_digest for item in self.modes}) != len(self.modes):
            raise ValueError("multi-dwell posterior mode identities must be unique")
        probabilities = tuple(item.posterior_probability for item in self.modes)
        if any(right > left for left, right in zip(probabilities, probabilities[1:], strict=False)):
            raise ValueError("multi-dwell posterior modes must be probability ordered")
        if not math.isclose(math.fsum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("positive multi-dwell mode probabilities must sum to one")
        normalizers = tuple(
            item.log_posterior_probability + item.cumulative_negative_log_joint
            for item in self.modes
        )
        if any(
            not math.isclose(item, normalizers[0], rel_tol=1e-12, abs_tol=1e-10)
            for item in normalizers[1:]
        ):
            raise ValueError("multi-dwell posterior probabilities disagree with scores")
        if any(
            tuple(item.dwell_id for item in mode.assignments) != self.dwell_ids
            or not set(mode.active_catalog_numbers) <= set(self.catalog_numbers)
            for mode in self.modes
        ):
            raise ValueError("multi-dwell mode inventory does not match the product")
        if (
            tuple(item.dwell_index for item in self.smoothed_identity_posteriors)
            != tuple(range(len(self.dwell_ids)))
            or tuple(item.dwell_id for item in self.smoothed_identity_posteriors) != self.dwell_ids
        ):
            raise ValueError("multi-dwell identity posterior inventory is inconsistent")
        if any(
            tuple(item.catalog_number for item in posterior.catalogue_probabilities)
            != self.catalog_numbers
            for posterior in self.smoothed_identity_posteriors
        ):
            raise ValueError("multi-dwell identity posterior lacks catalogue entries")
        self._validate_marginals()
        if self.retained_history_family_complete == self.any_beam_pruning:
            raise ValueError("multi-dwell retained-family completeness is inconsistent")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("multi-dwell posterior digest does not match content")
        return self

    def _validate_marginals(self) -> None:
        for index, posterior in enumerate(self.smoothed_identity_posteriors):
            derived: dict[int | None, float] = {
                None: 0.0,
                **{number: 0.0 for number in self.catalog_numbers},
            }
            for mode in self.modes:
                derived[mode.assignments[index].catalog_number] += mode.posterior_probability
            if not math.isclose(
                posterior.unassigned_probability,
                derived[None],
                rel_tol=0.0,
                abs_tol=1e-12,
            ) or any(
                not math.isclose(
                    item.posterior_probability,
                    derived[item.catalog_number],
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                for item in posterior.catalogue_probabilities
            ):
                raise ValueError("multi-dwell identity marginal disagrees with history modes")
