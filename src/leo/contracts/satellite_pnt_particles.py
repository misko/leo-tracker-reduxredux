"""Response-free geodetic particle bank for broad-prior blinded navigation."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import Matrix3, _validate_matrix3
from leo.contracts.sky import ObserverSiteV1


class GeodeticPositionParticleV1(ContractModel):
    schema_version: Literal[1] = 1
    particle_id: Sha256Digest
    position: ObserverSiteV1
    prior_probability: Annotated[float, Field(gt=0.0, le=1.0)]
    local_covariance_ecef_m2: Matrix3

    @field_validator("prior_probability")
    @classmethod
    def _finite_probability(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("particle prior probability must be finite")
        return value

    @model_validator(mode="after")
    def _particle_is_proper(self) -> Self:
        _validate_matrix3(self.local_covariance_ecef_m2, positive_definite=True)
        return self


class ResponseFreeGeodeticParticleBankV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["response-free-geodetic-particle-bank"] = "response-free-geodetic-particle-bank"
    algorithm_version: Literal["precommitted-geodetic-particle-bank-v1"] = (
        "precommitted-geodetic-particle-bank-v1"
    )
    prior_provenance_digest: Sha256Digest
    generation_protocol_digest: Sha256Digest
    produced_utc_ns: Annotated[int, Field(gt=0)]
    particles: Annotated[
        tuple[GeodeticPositionParticleV1, ...], Field(min_length=2, max_length=256)
    ]
    response_accessed: Literal[False] = False
    truth_accessed: Literal[False] = False
    global_coverage_claimed: Literal[False] = False
    posterior_conditional_on_particle_bank: Literal[True] = True
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def _bank_is_closed(self) -> Self:
        particle_ids = tuple(item.particle_id for item in self.particles)
        if particle_ids != tuple(sorted(set(particle_ids))):
            raise ValueError("geodetic particles must be unique and canonically ordered")
        if not math.isclose(
            math.fsum(item.prior_probability for item in self.particles),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("geodetic particle prior probabilities must sum to one")
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("geodetic particle-bank digest does not match content")
        return self
