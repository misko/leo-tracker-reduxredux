"""Separate position-run envelope; published continuous v1 remains immutable."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier


class PositionRunCheckpointV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["position_scan_run"] = "position_scan_run"
    protocol_version: Literal[6] = 6
    logical_targets: Literal[24] = 24
    physical_slots: Literal[8] = 8
    analysis_path: Literal["interior-position"] = "interior-position"
    run_id: Identifier
    configuration: dict[str, JsonValue]
    configuration_sha256: Sha256Digest
    host: str
    serial: str
    state: Literal["starting", "running", "stopped", "failed"]
    captured_windows: Annotated[int, Field(ge=0)] = 0
    durable_windows: Annotated[int, Field(ge=0)] = 0
    latest_targets: dict[str, JsonValue] = Field(default_factory=dict)
    device_terminal: dict[str, JsonValue] | None = None
    host_restoration: dict[str, JsonValue] | None = None
    fault: str | None = None
    updated_utc_ns: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _identity(self) -> Self:
        if (
            canonical_digest(self.configuration) != self.configuration_sha256
            or len(self.latest_targets) > 24
            or self.durable_windows > self.captured_windows
        ):
            raise ValueError("position checkpoint identity or counters changed")
        if self.state == "stopped" and (not self.device_terminal or not self.host_restoration):
            raise ValueError("stopped position run requires terminal and restoration evidence")
        return self
