"""Exact joint hypotheses over several frozen single-emitter corrections.

Each source slot carries one complete ``SatelliteCorrectionProductV1``.  Its
mode and unassigned probabilities remain local to that slot.  This contract
forms the exact Cartesian product, rejects assignments that give two
simultaneous slots the same catalogue object, and renormalizes only after that
explicit exclusivity constraint.  It does not claim that the originating slot
posteriors are independent in reality: that approximation and the absence of a
joint shared-calibration nuisance model are persisted as hard claim limits.
"""

from __future__ import annotations

import itertools
import math
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier
from leo.contracts.satellite_pnt import SatelliteCorrectionProductV1

_MAXIMUM_EXACT_HYPOTHESES = 4096


class FrozenCorrectionSourceSlotV1(ContractModel):
    schema_version: Literal[1] = 1
    slot_id: Identifier
    correction_product: SatelliteCorrectionProductV1

    @model_validator(mode="after")
    def _slot_is_valid(self) -> Self:
        SatelliteCorrectionProductV1.model_validate(self.correction_product.model_dump(mode="json"))
        return self


class JointCorrectionSlotAssignmentV1(ContractModel):
    schema_version: Literal[1] = 1
    slot_id: Identifier
    selected_mode_digest: Sha256Digest | None
    selected_catalog_number: Annotated[int, Field(gt=0)] | None

    @model_validator(mode="after")
    def _selection_is_all_or_none(self) -> Self:
        if (self.selected_mode_digest is None) != (self.selected_catalog_number is None):
            raise ValueError("joint correction assignment must select both mode and catalogue")
        return self


class JointCorrectionHypothesisV1(ContractModel):
    schema_version: Literal[1] = 1
    assignments: Annotated[
        tuple[JointCorrectionSlotAssignmentV1, ...], Field(min_length=1, max_length=8)
    ]
    active_catalog_numbers: Annotated[tuple[int, ...], Field(max_length=8)]
    posterior_probability: Annotated[float, Field(gt=0.0, le=1.0)]
    hypothesis_digest: Sha256Digest

    @field_validator("posterior_probability")
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("joint correction probability must be finite")
        return value

    @model_validator(mode="after")
    def _hypothesis_is_closed(self) -> Self:
        slot_ids = tuple(item.slot_id for item in self.assignments)
        if slot_ids != tuple(sorted(set(slot_ids))):
            raise ValueError("joint correction assignments must be unique and ordered")
        derived_catalogues = tuple(
            sorted(
                item.selected_catalog_number
                for item in self.assignments
                if item.selected_catalog_number is not None
            )
        )
        if len(set(derived_catalogues)) != len(derived_catalogues):
            raise ValueError("simultaneous slots cannot select the same catalogue")
        if self.active_catalog_numbers != derived_catalogues:
            raise ValueError("active catalogue inventory does not match assignments")
        expected_digest = canonical_digest(
            tuple(item.model_dump(mode="json") for item in self.assignments)
        )
        if self.hypothesis_digest != expected_digest:
            raise ValueError("joint correction hypothesis digest does not match assignments")
        return self


class SatelliteCorrectionHypothesisSetV1(ContractModel):
    """Complete bounded joint family under an explicit slot-independence model."""

    schema_version: Literal[1] = 1
    kind: Literal["satellite-correction-hypothesis-set"] = "satellite-correction-hypothesis-set"
    algorithm_version: Literal["exact-independent-slot-product-v1"] = (
        "exact-independent-slot-product-v1"
    )
    jointing_protocol_digest: Sha256Digest
    source_slots: Annotated[
        tuple[FrozenCorrectionSourceSlotV1, ...], Field(min_length=1, max_length=8)
    ]
    hypotheses: Annotated[
        tuple[JointCorrectionHypothesisV1, ...],
        Field(min_length=1, max_length=_MAXIMUM_EXACT_HYPOTHESES),
    ]
    source_hypothesis_count: Annotated[int, Field(gt=0, le=_MAXIMUM_EXACT_HYPOTHESES)]
    target_response_accessed: Literal[False] = False
    catalogue_exclusivity_enforced: Literal[True] = True
    slot_posterior_independence_assumed: Literal[True] = True
    shared_calibration_nuisance_jointly_modeled: Literal[False] = False
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _family_is_exact_and_closed(self) -> Self:
        slots = tuple(
            FrozenCorrectionSourceSlotV1.model_validate(item.model_dump(mode="json"))
            for item in self.source_slots
        )
        slot_ids = tuple(item.slot_id for item in slots)
        if slot_ids != tuple(sorted(set(slot_ids))):
            raise ValueError("joint correction source slots must be unique and ordered")
        product_digests = tuple(item.correction_product.content_digest for item in slots)
        if len(set(product_digests)) != len(product_digests):
            raise ValueError("joint correction source slots repeat a product")

        expected = _derive_exact_hypotheses(slots)
        if self.source_hypothesis_count != len(expected):
            raise ValueError("joint correction hypothesis count is not exact")
        if len(self.hypotheses) != len(expected):
            raise ValueError("joint correction family is truncated or padded")
        actual_keys = tuple(_hypothesis_key(item) for item in self.hypotheses)
        expected_keys = tuple(_hypothesis_key(item) for item in expected)
        if actual_keys != expected_keys:
            raise ValueError("joint correction hypothesis inventory or ordering is not exact")
        for actual, derived in zip(self.hypotheses, expected, strict=True):
            if not math.isclose(
                actual.posterior_probability,
                derived.posterior_probability,
                rel_tol=1e-12,
                abs_tol=1e-15,
            ):
                raise ValueError("joint correction posterior probability is inconsistent")
        if not math.isclose(
            math.fsum(item.posterior_probability for item in self.hypotheses),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("joint correction posterior probabilities must sum to one")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("joint correction hypothesis-set digest does not match content")
        return self


def derive_joint_correction_hypotheses(
    source_slots: tuple[FrozenCorrectionSourceSlotV1, ...],
) -> tuple[JointCorrectionHypothesisV1, ...]:
    """Public pure constructor used by the fail-closed builder and tests."""

    slots = tuple(
        FrozenCorrectionSourceSlotV1.model_validate(item.model_dump(mode="json"))
        for item in source_slots
    )
    return _derive_exact_hypotheses(slots)


def _derive_exact_hypotheses(
    slots: tuple[FrozenCorrectionSourceSlotV1, ...],
) -> tuple[JointCorrectionHypothesisV1, ...]:
    choice_families = tuple(_slot_choices(item) for item in slots)
    upper_bound = 1
    for choices in choice_families:
        upper_bound *= len(choices)
        if upper_bound > _MAXIMUM_EXACT_HYPOTHESES:
            raise ValueError("joint correction exact-family work bound exceeded")

    feasible: list[tuple[tuple[JointCorrectionSlotAssignmentV1, ...], float]] = []
    for combination in itertools.product(*choice_families):
        assignments = tuple(item[0] for item in combination)
        active = tuple(
            item.selected_catalog_number
            for item in assignments
            if item.selected_catalog_number is not None
        )
        if len(set(active)) != len(active):
            continue
        log_weight = math.fsum(item[1] for item in combination)
        if not math.isfinite(log_weight):
            raise ValueError("joint correction log weight is not finite")
        feasible.append((assignments, log_weight))
    if not feasible:
        raise ValueError("joint correction family has no feasible hypothesis")

    maximum = max(item[1] for item in feasible)
    shifted = tuple(math.exp(item[1] - maximum) for item in feasible)
    normalizer = math.fsum(shifted)
    if not math.isfinite(normalizer) or normalizer <= 0.0:
        raise ValueError("joint correction normalization is not representable")
    hypotheses = tuple(
        JointCorrectionHypothesisV1(
            assignments=assignments,
            active_catalog_numbers=tuple(
                sorted(
                    item.selected_catalog_number
                    for item in assignments
                    if item.selected_catalog_number is not None
                )
            ),
            posterior_probability=weight / normalizer,
            hypothesis_digest=canonical_digest(
                tuple(item.model_dump(mode="json") for item in assignments)
            ),
        )
        for (assignments, _log_weight), weight in zip(feasible, shifted, strict=True)
    )
    return tuple(sorted(hypotheses, key=_hypothesis_key))


def _slot_choices(
    slot: FrozenCorrectionSourceSlotV1,
) -> tuple[tuple[JointCorrectionSlotAssignmentV1, float], ...]:
    product = slot.correction_product
    choices: list[tuple[JointCorrectionSlotAssignmentV1, float]] = []
    if product.unassigned_probability > 0.0:
        choices.append(
            (
                JointCorrectionSlotAssignmentV1(
                    slot_id=slot.slot_id,
                    selected_mode_digest=None,
                    selected_catalog_number=None,
                ),
                math.log(product.unassigned_probability),
            )
        )
    for mode in product.modes:
        choices.append(
            (
                JointCorrectionSlotAssignmentV1(
                    slot_id=slot.slot_id,
                    selected_mode_digest=mode.mode_digest,
                    selected_catalog_number=mode.catalog_number,
                ),
                math.log(mode.posterior_probability),
            )
        )
    if not choices:
        raise ValueError("joint correction slot has no positive-probability choice")
    return tuple(choices)


def _hypothesis_key(item: JointCorrectionHypothesisV1) -> tuple[float, tuple[str, ...]]:
    assignment_key = tuple(assignment.selected_mode_digest or "" for assignment in item.assignments)
    return (-item.posterior_probability, assignment_key)
