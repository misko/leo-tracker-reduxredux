"""Additive V2 odd-Qin response ledger with retained specificity evidence.

V1 remains byte- and behavior-compatible: its no-support state is value-free.
This V2 contract adds the measured-but-ineligible state needed by the final
holdout while retaining every frozen target in the denominator.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from leo.analysis.research.doppler_holdout_pre_response import (
    AccuracyDisposition,
    DopplerHoldoutPredictionLedgerV1,
    ForecastTargetKeyV1,
    OddQinResponseRequestV1,
    OddQinTargetAuthorityV1,
    ReasonCode,
    ResponseStatus,
)
from leo.contracts.digests import Sha256Digest, canonical_digest

ODD_ATTACHMENT_SCHEMA_V2 = "org.leo.research.doppler-holdout-odd-attachment/v2"


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class OddQinResponseMeasurementV2(_ResponseModel):
    prediction_ledger_digest: Sha256Digest
    target: ForecastTargetKeyV1
    status: ResponseStatus
    missing_reason: ReasonCode | None = None
    support_reasons: tuple[ReasonCode, ...] = ()
    accuracy_disposition: AccuracyDisposition
    odd_absolute_cfo_hz: float | None = None
    odd_frequency_uncertainty_hz: float | None = None
    odd_exact_coherence: float | None = None
    odd_rolled_control_coherence: float | None = None
    odd_coherence_margin: float | None = None
    odd_phase_residual_rms_rad: float | None = None
    odd_search_boundary: bool | None = None

    @model_validator(mode="after")
    def _response_is_closed(self) -> Self:
        values = (
            self.odd_absolute_cfo_hz,
            self.odd_frequency_uncertainty_hz,
            self.odd_exact_coherence,
            self.odd_rolled_control_coherence,
            self.odd_coherence_margin,
            self.odd_phase_residual_rms_rad,
        )
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("odd-Qin response value must be finite")
        complete = all(value is not None for value in values)
        any_value = any(value is not None for value in values)
        if self.status in {"finite", "boundary", "no_support"}:
            if self.missing_reason is not None or not complete:
                raise ValueError("measured response requires all specificity fields")
            expected_boundary = self.status == "boundary"
            if self.odd_search_boundary is not expected_boundary:
                raise ValueError("odd-Qin boundary status and flag disagree")
            if self.status == "finite" and (
                self.support_reasons or self.accuracy_disposition != "eligible"
            ):
                raise ValueError("finite odd response disposition disagrees")
            if self.status == "boundary" and (
                self.support_reasons or self.accuracy_disposition != "excluded_boundary"
            ):
                raise ValueError("boundary odd response disposition disagrees")
            if self.status == "no_support" and (
                not self.support_reasons or self.accuracy_disposition != "excluded_no_support"
            ):
                raise ValueError("no-support odd response requires reasons")
        elif (
            self.missing_reason is None
            or self.support_reasons
            or any_value
            or self.odd_search_boundary is not None
            or self.accuracy_disposition != "missing"
        ):
            raise ValueError("missing odd response requires one reason and no values")
        if self.status != "missing":
            uncertainty = self.odd_frequency_uncertainty_hz
            exact = self.odd_exact_coherence
            control = self.odd_rolled_control_coherence
            margin = self.odd_coherence_margin
            phase_rms = self.odd_phase_residual_rms_rad
            if uncertainty is None or uncertainty <= 0:
                raise ValueError("odd frequency uncertainty must be positive")
            if exact is None or control is None or not 0 <= exact <= 1 or not 0 <= control <= 1:
                raise ValueError("odd coherences must lie in [0, 1]")
            if margin is None or not math.isclose(margin, exact - control, abs_tol=1e-12):
                raise ValueError("odd coherence margin disagrees")
            if phase_rms is None or phase_rms < 0:
                raise ValueError("odd phase residual RMS must be non-negative")
        return self


class OddQinResponsePortV2(Protocol):
    def measure_odd_qin(self, request: OddQinResponseRequestV1) -> OddQinResponseMeasurementV2:
        """Measure the exact held-out odd fold."""


class OddQinAttachmentRowV2(_ResponseModel):
    target: ForecastTargetKeyV1
    prediction_ledger_digest: Sha256Digest
    membership_mutated: Literal[False] = False
    response_denominator_member: Literal[True] = True
    response: OddQinResponseMeasurementV2

    @model_validator(mode="after")
    def _row_matches(self) -> Self:
        if self.response.target != self.target:
            raise ValueError("attached response target disagrees")
        if self.response.prediction_ledger_digest != self.prediction_ledger_digest:
            raise ValueError("attached prediction digest disagrees")
        return self


class OddQinAttachmentLedgerV2(_ResponseModel):
    schema: Literal["org.leo.research.doppler-holdout-odd-attachment/v2"]  # type: ignore[assignment]
    prediction_ledger_digest: Sha256Digest
    prediction_membership_or_values_mutated: Literal[False]
    target_count: Annotated[int, Field(gt=0)]
    finite_response_count: Annotated[int, Field(ge=0)]
    accuracy_eligible_count: Annotated[int, Field(ge=0)]
    boundary_response_count: Annotated[int, Field(ge=0)]
    no_support_response_count: Annotated[int, Field(ge=0)]
    missing_response_count: Annotated[int, Field(ge=0)]
    rows: tuple[OddQinAttachmentRowV2, ...]
    attachment_digest: Sha256Digest

    @model_validator(mode="after")
    def _ledger_is_closed(self) -> Self:
        identities = tuple(row.target.identity() for row in self.rows)
        if len(self.rows) != self.target_count or len(set(identities)) != len(identities):
            raise ValueError("V2 response target accounting disagrees")
        statuses = tuple(row.response.status for row in self.rows)
        expected = (
            sum(status in {"finite", "boundary", "no_support"} for status in statuses),
            sum(row.response.accuracy_disposition == "eligible" for row in self.rows),
            statuses.count("boundary"),
            statuses.count("no_support"),
            statuses.count("missing"),
        )
        actual = (
            self.finite_response_count,
            self.accuracy_eligible_count,
            self.boundary_response_count,
            self.no_support_response_count,
            self.missing_response_count,
        )
        if expected != actual or sum(actual[1:]) != self.target_count:
            raise ValueError("V2 response status accounting disagrees")
        if any(row.prediction_ledger_digest != self.prediction_ledger_digest for row in self.rows):
            raise ValueError("V2 response row uses another prediction ledger")
        content = self.model_dump(mode="json", exclude={"attachment_digest"})
        if self.attachment_digest != canonical_digest(content):
            raise ValueError("V2 response ledger digest disagrees")
        return self


def attach_odd_qin_responses_v2(
    prediction: DopplerHoldoutPredictionLedgerV1,
    authorities: tuple[OddQinTargetAuthorityV1, ...],
    port: OddQinResponsePortV2,
) -> OddQinAttachmentLedgerV2:
    authority_by_key = {item.target.identity(): item for item in authorities}
    expected_keys = tuple(row.target.identity() for row in prediction.rows)
    if len(authority_by_key) != len(authorities) or set(authority_by_key) != set(expected_keys):
        raise ValueError("V2 response authority inventory disagrees")
    rows: list[OddQinAttachmentRowV2] = []
    for prediction_row in prediction.rows:
        request = OddQinResponseRequestV1(
            prediction_ledger_digest=prediction.ledger_digest,
            authority=authority_by_key[prediction_row.target.identity()],
        )
        response = port.measure_odd_qin(request)
        rows.append(
            OddQinAttachmentRowV2(
                target=prediction_row.target,
                prediction_ledger_digest=prediction.ledger_digest,
                response=response,
            )
        )
    document = {
        "schema": ODD_ATTACHMENT_SCHEMA_V2,
        "prediction_ledger_digest": prediction.ledger_digest,
        "prediction_membership_or_values_mutated": False,
        "target_count": len(rows),
        "finite_response_count": sum(
            row.response.status in {"finite", "boundary", "no_support"} for row in rows
        ),
        "accuracy_eligible_count": sum(
            row.response.accuracy_disposition == "eligible" for row in rows
        ),
        "boundary_response_count": sum(row.response.status == "boundary" for row in rows),
        "no_support_response_count": sum(row.response.status == "no_support" for row in rows),
        "missing_response_count": sum(row.response.status == "missing" for row in rows),
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    return OddQinAttachmentLedgerV2.model_validate(
        {**document, "attachment_digest": canonical_digest(document)}
    )
