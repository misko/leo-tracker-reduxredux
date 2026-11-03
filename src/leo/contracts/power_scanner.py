"""Standalone metadata-only FPGA measurements, distinct from all IQ contracts."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.recording import Identifier

U64 = Annotated[int, Field(ge=0, lt=1 << 64)]
S64 = Annotated[int, Field(ge=-(1 << 63), lt=1 << 63)]


class StandaloneReceiverPowerV1(ContractModel):
    receiver_id: Literal[0, 1]
    energy_sum: U64
    sum_i: S64
    sum_q: S64
    clipping_i: Annotated[int, Field(ge=0, le=50_000)]
    clipping_q: Annotated[int, Field(ge=0, le=50_000)]
    adc12_contact_samples: Annotated[int, Field(ge=0, le=50_000)]
    peak_abs_component: Annotated[int, Field(ge=0, le=32768)]
    decision: Literal["unknown", "active", "quiet"]


class StandalonePowerResultV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["standalone_fpga_power_measurement"] = "standalone_fpga_power_measurement"
    sequence: U64
    session: Annotated[int, Field(gt=0, lt=1 << 32)]
    generation: Annotated[int, Field(gt=0, lt=1 << 32)]
    visit: U64
    sweep: U64
    target_index: Annotated[int, Field(ge=0, lt=8)]
    profile: Annotated[int, Field(ge=0, lt=8)]
    sample_rate_hz: Literal[2_500_000] = 2_500_000
    sample_start: U64
    sample_end_exclusive: U64
    sample_count: Annotated[int, Field(ge=0, le=50_000)]
    counter_authority: Literal["hardware"] = "hardware"
    counter_identity: Literal["prepack_preincrement_v1"] = "prepack_preincrement_v1"
    flags: Annotated[int, Field(ge=0, le=255)]
    complete: bool
    recall: dict[str, int]
    table_sha256: Sha256Digest
    table_digest_authority: Literal["host_declared"] = "host_declared"
    guard_identity: Literal["post-recall-guard-v1"] = "post-recall-guard-v1"
    guard_samples: Annotated[int, Field(gt=0)]
    datapath_caps: Annotated[int, Field(ge=0, le=3)] | None = None
    adc12_qualified: bool
    threshold_energy: tuple[U64, U64]
    threshold_rounding_rule: Literal["ceil-ci16-energy-v1"] = "ceil-ci16-energy-v1"
    receivers: tuple[StandaloneReceiverPowerV1, StandaloneReceiverPowerV1]

    @model_validator(mode="after")
    def _evidence(self) -> Self:
        if self.sample_end_exclusive < self.sample_start:
            raise ValueError("standalone power interval regressed")
        complete = (
            self.flags == 0
            and self.sample_count == 50_000
            and self.sample_end_exclusive - self.sample_start == self.sample_count
        )
        if self.complete != complete or tuple(
            receiver.receiver_id for receiver in self.receivers
        ) != (0, 1):
            raise ValueError("standalone power completion/receiver geometry changed")
        if (not self.complete or not self.adc12_qualified) and any(
            receiver.decision != "unknown" for receiver in self.receivers
        ):
            raise ValueError("unqualified or invalid power cannot claim activity")
        for receiver in self.receivers:
            if (
                receiver.clipping_i
                or receiver.clipping_q
                or (self.adc12_qualified and receiver.adc12_contact_samples)
            ) and receiver.decision != "unknown":
                raise ValueError("clipped power cannot claim activity")
        return self


class StandalonePowerCheckpointV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["standalone_fpga_power_run"] = "standalone_fpga_power_run"
    run_id: Identifier
    host: str
    serial: str
    session: Annotated[int, Field(gt=0, lt=1 << 32)]
    generation: Annotated[int, Field(gt=0, lt=1 << 32)]
    state: Literal["prepared", "running", "stopped", "recovery_required", "failed"]
    preparation: dict[str, JsonValue]
    request: dict[str, JsonValue]
    device_status: dict[str, JsonValue] | None = None
    host_restoration: dict[str, JsonValue] | None = None
    fault: str | None = None
    updated_utc_ns: Annotated[int, Field(ge=0)]
