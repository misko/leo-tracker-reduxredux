"""Narrow in-memory port and immutable manifest for calibrated T1-AT orbit banks."""

from dataclasses import dataclass
from typing import Literal, Self

import numpy as np
from pydantic import model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.t1_at import T1AtInputV1


class T1AtDiscoveryManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    analysis_id: Literal["t1-at-discovery-input-v1"] = "t1-at-discovery-input-v1"
    evidence: T1AtInputV1
    bank_sha256: Sha256Digest
    array_file: Literal["prediction-bank.npz"] = "prediction-bank.npz"
    calibration_scope: Literal["frozen-receiver-rf-at-receive-time"] = (
        "frozen-receiver-rf-at-receive-time"
    )

    @model_validator(mode="after")
    def no_prediscovery(self) -> Self:
        if self.evidence.fitted_c_modes or self.evidence.zero_c_modes:
            raise ValueError("discovery input must not contain preselected timing modes")
        return self


@dataclass(frozen=True)
class T1AtDiscoveryData:
    manifest: T1AtDiscoveryManifestV1
    candidate_ids: np.ndarray
    numbers: np.ndarray
    nodes_s: np.ndarray
    position_km: np.ndarray
    velocity_km_s: np.ndarray
    rf_hz: np.ndarray
    observer_km: np.ndarray  # arm, observation, xyz
    up: np.ndarray  # arm, observation, xyz
    calibration_hz: np.ndarray  # arm, observation, evaluated at receive time
