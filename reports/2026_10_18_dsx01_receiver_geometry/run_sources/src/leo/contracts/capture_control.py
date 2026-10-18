"""Versioned operator control state for every radio capture producer."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel

ControlText = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class CaptureDesiredState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"


class CaptureObservedState(StrEnum):
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"


class CaptureControlStateV1(ContractModel):
    """Durable capture admission fence shared by acquisition and scanning."""

    schema_version: Literal[1] = 1
    generation: Annotated[int, Field(ge=0)]
    desired_state: CaptureDesiredState
    observed_state: CaptureObservedState
    changed_utc_ns: Annotated[int, Field(ge=0)]
    operator_id: ControlText
    reason: ControlText

    @model_validator(mode="after")
    def _states_agree(self) -> Self:
        if self.desired_state is CaptureDesiredState.RUNNING:
            if self.observed_state is not CaptureObservedState.RUNNING:
                raise ValueError("running capture desire requires running observation")
        elif self.observed_state is CaptureObservedState.RUNNING:
            raise ValueError("paused capture desire cannot be observed running")
        return self
