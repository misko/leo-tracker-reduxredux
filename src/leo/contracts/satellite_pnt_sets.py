"""Additive multi-satellite correction-set contract.

``SatelliteCorrectionProductV1`` is intentionally a probability simplex for
one emitter: its modes are alternative catalogue identities and their
probabilities, together with an unassigned probability, sum to one.  A
navigation solve instead consumes several simultaneously available emitters.
Those are different semantics and must not be represented by renormalizing
single-emitter alternatives into one product.

This module adds a narrow oracle/precommitted selection boundary.  Each slot
retains its complete, independently sealed single-emitter product and names one
eligible mode selected by an external identity authority.  Probabilities remain
local to their originating product; the set does not reinterpret them as a
cross-satellite distribution.  The contract contains no calibration receipt,
site coordinates, or receiver-local state.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier
from leo.contracts.satellite_pnt import SatelliteCorrectionProductV1
from leo.contracts.standard_pipeline import StandardScientificStatus


class FrozenSatelliteCorrectionSelectionV1(ContractModel):
    """One externally selected, navigation-eligible single-emitter mode."""

    schema_version: Literal[1] = 1
    slot_id: Identifier
    correction_product: SatelliteCorrectionProductV1
    selected_mode_digest: Sha256Digest
    selected_catalog_number: Annotated[int, Field(gt=0)]
    selection_evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def _selection_is_closed(self) -> Self:
        product = SatelliteCorrectionProductV1.model_validate(
            self.correction_product.model_dump(mode="json")
        )
        if product.status is not StandardScientificStatus.COMPLETE:
            raise ValueError("a correction-set selection requires a complete product")
        matches = tuple(
            mode for mode in product.modes if mode.mode_digest == self.selected_mode_digest
        )
        if len(matches) != 1:
            raise ValueError("selected correction mode does not resolve exactly once")
        selected = matches[0]
        if selected.catalog_number != self.selected_catalog_number:
            raise ValueError("selected catalogue number does not match the correction mode")
        if not selected.navigation_eligible:
            raise ValueError("selected correction mode is not navigation eligible")
        return self


class SatelliteCorrectionSetV1(ContractModel):
    """Solver-safe simultaneous corrections selected before target response.

    V1 deliberately supports only an externally frozen one-mode-per-slot
    selection.  It is suitable for the oracle-identity positioning lane and for
    testing the calibration-to-navigation boundary.  Unknown-identity joint
    hypotheses require a later additive contract that preserves assignment
    probabilities and exclusivity rather than collapsing them here.
    """

    schema_version: Literal[1] = 1
    kind: Literal["satellite-correction-set"] = "satellite-correction-set"
    algorithm_version: Literal["oracle-selected-independent-products-v1"] = (
        "oracle-selected-independent-products-v1"
    )
    selection_authority_digest: Sha256Digest
    selection_policy: Literal["response-free-precommitted-oracle-v1"] = (
        "response-free-precommitted-oracle-v1"
    )
    members: Annotated[
        tuple[FrozenSatelliteCorrectionSelectionV1, ...],
        Field(min_length=1, max_length=64),
    ]
    produced_utc_ns: Annotated[int, Field(gt=0)]
    valid_from_utc_ns: Annotated[int, Field(gt=0)]
    valid_until_utc_ns: Annotated[int, Field(gt=0)]
    downlink_frequency_hz: Annotated[float, Field(gt=0.0)]
    calibration_site_disclosed: Literal[False] = False
    receiver_local_state_excluded: Literal[True] = True
    local_state_treatment: Literal["marginalized-in-origin-products-v1"] = (
        "marginalized-in-origin-products-v1"
    )
    simultaneous_probability_semantics: Literal[
        "per-slot-probabilities-not-renormalized-across-satellites-v1"
    ] = "per-slot-probabilities-not-renormalized-across-satellites-v1"
    unknown_identity_joint_hypotheses_supported: Literal[False] = False
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _set_is_closed(self) -> Self:
        if self.valid_until_utc_ns <= self.valid_from_utc_ns:
            raise ValueError("correction-set validity interval must be non-empty")
        keys = tuple(item.slot_id for item in self.members)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("correction-set slots must be unique and canonically ordered")

        products = tuple(
            SatelliteCorrectionProductV1.model_validate(
                item.correction_product.model_dump(mode="json")
            )
            for item in self.members
        )
        product_digests = tuple(item.content_digest for item in products)
        selected_mode_digests = tuple(item.selected_mode_digest for item in self.members)
        selected_catalog_numbers = tuple(item.selected_catalog_number for item in self.members)
        if len(set(selected_catalog_numbers)) != len(selected_catalog_numbers):
            raise ValueError("simultaneous correction slots must select distinct catalogues")
        if len(set(product_digests)) != len(product_digests):
            raise ValueError("correction set repeats a single-emitter product")
        if len(set(selected_mode_digests)) != len(selected_mode_digests):
            raise ValueError("correction set repeats a selected mode")

        expected_produced = max(item.produced_utc_ns for item in products)
        selected_modes = tuple(
            next(mode for mode in product.modes if mode.mode_digest == member.selected_mode_digest)
            for member, product in zip(self.members, products, strict=True)
        )
        expected_valid_from = max(item.valid_from_utc_ns for item in selected_modes)
        expected_valid_until = min(item.valid_until_utc_ns for item in selected_modes)
        if expected_valid_until <= expected_valid_from:
            raise ValueError("selected correction modes have no common validity interval")
        if self.produced_utc_ns != expected_produced:
            raise ValueError("correction-set production time does not close over its products")
        if (
            self.valid_from_utc_ns != expected_valid_from
            or self.valid_until_utc_ns != expected_valid_until
        ):
            raise ValueError("correction-set validity does not equal the mode intersection")
        if any(item.produced_utc_ns > self.valid_from_utc_ns for item in products):
            raise ValueError("correction-set validity predates an origin product")
        if any(item.downlink_frequency_hz != self.downlink_frequency_hz for item in products):
            raise ValueError("correction-set products use different downlink frequencies")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("satellite correction-set digest does not match content")
        return self
