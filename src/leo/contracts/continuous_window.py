"""Additive continuous-run checkpoints; sealed IQ segments remain version one."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier


class ContinuousRunCheckpointV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["continuous_short_window_run"] = "continuous_short_window_run"
    run_id: Identifier
    configuration: dict[str, JsonValue]
    configuration_sha256: Sha256Digest
    host: str
    serial: str
    process_id: Annotated[int, Field(ge=0)] = 0
    device_session: Annotated[int, Field(ge=0, lt=1 << 64)] = 0
    generation: Annotated[int, Field(ge=0, lt=1 << 64)] = 0
    state: Literal["starting", "running", "stop_requested", "draining", "stopped", "failed"]
    captured_windows: Annotated[int, Field(ge=0, lt=1 << 64)] = 0
    durable_windows: Annotated[int, Field(ge=0, lt=1 << 64)] = 0
    sealed_segments: Annotated[int, Field(ge=0)] = 0
    latest_segment_id: Identifier | None = None
    device_terminal: dict[str, JsonValue] | None = None
    host_restoration: dict[str, JsonValue] | None = None
    latest_targets: dict[str, JsonValue] = Field(default_factory=dict)
    writer_backlog_windows: Annotated[int, Field(ge=0)] = 0
    writer_backlog_bytes: Annotated[int, Field(ge=0)] = 0
    fault: str | None = None
    updated_utc_ns: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _configuration_identity(self) -> Self:
        if canonical_digest(self.configuration) != self.configuration_sha256:
            raise ValueError("continuous configuration digest mismatch")
        if len(self.latest_targets) > 8 or self.durable_windows > self.captured_windows:
            raise ValueError("continuous checkpoint counters or target retention changed")
        return self
