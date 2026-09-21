"""Truthful, bounded positioning diagnostics for one scanner capture.

The diagnostic is deliberately conditional on the site-assisted satellite
identity used by the solver.  It is evidence about a bounded optimization,
not an independent position fix.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest


class RegionPositionPriorV1(ContractModel):
    center_latitude_deg: Annotated[float, Field(ge=-90.0, le=90.0)]
    center_longitude_deg: Annotated[float, Field(ge=-180.0, le=180.0)]
    width_km: Annotated[float, Field(gt=0.0)]
    height_km: Annotated[float, Field(gt=0.0)]
    altitude_m: Annotated[float, Field(ge=-500.0, le=100_000.0)]

    @model_validator(mode="after")
    def _finite_and_bounded(self) -> Self:
        values = (
            self.center_latitude_deg,
            self.center_longitude_deg,
            self.width_km,
            self.height_km,
            self.altitude_m,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("position prior values must be finite")
        return self


class SparseScanPositionDiagnosticV1(ContractModel):
    schema_version: Literal[1] = 1
    state: Literal["insufficient", "diagnostic", "failed"]
    conditional_on_site_assisted_identity: Literal[True] = True
    position_fix_claimed: Literal[False] = False
    position_prior: RegionPositionPriorV1
    source_count: Annotated[int, Field(ge=0)]
    track_count: Annotated[int, Field(ge=0)]
    fit_observation_count: Annotated[int, Field(ge=0)]
    evaluation_observation_count: Annotated[int, Field(ge=0)]
    selected_observation_ids: tuple[str, ...] = ()
    selected_observations_digest: Sha256Digest
    configuration_digest: Sha256Digest
    candidate_latitude_deg: Annotated[float, Field(ge=-90.0, le=90.0)] | None = None
    candidate_longitude_deg: Annotated[float, Field(ge=-180.0, le=180.0)] | None = None
    training_rms_hz: Annotated[float, Field(ge=0.0)] | None = None
    evaluation_rms_hz: Annotated[float, Field(ge=0.0)] | None = None
    jacobian_rank: Annotated[int, Field(ge=0, le=2)] | None = None
    condition_number: Annotated[float, Field(ge=1.0)] | None = None
    boundary_hit: bool | None = None
    reasons: tuple[str, ...] = ()
    runtime_ms: Annotated[float, Field(ge=0.0)]

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.fit_observation_count + self.evaluation_observation_count != len(
            self.selected_observation_ids
        ):
            raise ValueError("selected position observation accounting differs")
        if len(set(self.selected_observation_ids)) != len(self.selected_observation_ids) or any(
            not item.strip() for item in self.selected_observation_ids
        ):
            raise ValueError("selected position observation IDs must be unique and non-empty")
        optional_numbers = (
            self.candidate_latitude_deg,
            self.candidate_longitude_deg,
            self.training_rms_hz,
            self.evaluation_rms_hz,
            self.condition_number,
        )
        if not math.isfinite(self.runtime_ms) or any(
            value is not None and not math.isfinite(value) for value in optional_numbers
        ):
            raise ValueError("position diagnostic numbers must be finite")
        candidate_fields = (
            self.candidate_latitude_deg,
            self.candidate_longitude_deg,
            self.training_rms_hz,
            self.evaluation_rms_hz,
            self.jacobian_rank,
            self.condition_number,
            self.boundary_hit,
        )
        if self.state == "diagnostic":
            if any(value is None for value in candidate_fields):
                raise ValueError("diagnostic position result is incomplete")
        elif any(value is not None for value in candidate_fields):
            raise ValueError("non-diagnostic position state cannot publish a candidate")
        if self.state != "diagnostic" and not self.reasons:
            raise ValueError("non-diagnostic position state requires a reason")
        return self


def insufficient_scan_position_diagnostic(
    *,
    position_prior: RegionPositionPriorV1,
    selected_observations_digest: str,
    configuration_digest: str,
    reasons: tuple[str, ...],
    runtime_ms: float = 0.0,
) -> SparseScanPositionDiagnosticV1:
    """Build an explicit empty diagnostic for an unavailable analyzer."""
    return SparseScanPositionDiagnosticV1(
        state="insufficient",
        position_prior=position_prior,
        source_count=0,
        track_count=0,
        fit_observation_count=0,
        evaluation_observation_count=0,
        selected_observation_ids=(),
        selected_observations_digest=selected_observations_digest,
        configuration_digest=configuration_digest,
        reasons=reasons,
        runtime_ms=runtime_ms,
    )
