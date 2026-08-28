"""Explicit gain-controller authority and tandem metadata evidence."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest


class GainControllerMode(StrEnum):
    """Controllers that can produce counter-authoritative ABI3 captures."""

    TANDEM_HOLD = "tandem_hold"
    TANDEM_AUTO = "tandem_auto"


class GainControllerPolicyV1(ContractModel):
    """One complete, immutable tandem session request for a physical radio."""

    schema_version: Literal[1] = 1
    request_digest: Sha256Digest
    mode: GainControllerMode
    controller_receiver_ids: tuple[Literal[0], Literal[1]] = (0, 1)
    observation_capacity: Literal[64] = 64
    event_capacity: Literal[64] = 64
    minimum_gain_db: Literal[0] = 0
    maximum_gain_db: Literal[62] = 62
    initial_gain_db: Literal[30] = 30
    power_measurement_samples: Literal[1024] = 1024
    low_power_dwell_periods: Literal[3] = 3
    cooldown_periods: Annotated[int, Field(ge=16)] = 16
    pulse_high_cycles: Literal[4] = 4
    pulse_low_cycles: Literal[4] = 4
    detector_blanking_cycles: Literal[8] = 8
    low_power_threshold: Literal[20] = 20
    large_lmt_overload_threshold: Literal[58] = 58
    large_adc_overload_threshold: Literal[49] = 49
    small_adc_overload_threshold: Literal[48] = 48

    @model_validator(mode="after")
    def _digest_matches_request(self) -> Self:
        expected = gain_controller_policy_digest(self)
        if self.request_digest != expected:
            raise ValueError(f"gain-controller request digest does not match content: {expected}")
        return self

    @classmethod
    def create(
        cls,
        mode: GainControllerMode,
        *,
        sample_count: int,
    ) -> GainControllerPolicyV1:
        if sample_count <= 0:
            raise ValueError("gain-controller sample count must be positive")
        # Match PPU's V2 capacity proof: the fixed event array must cover the
        # first-refill arm window as well as the refill being returned. HOLD
        # retains the same reviewed request so both modes share one authority.
        retention_samples = sample_count * 2
        minimum_periods = (retention_samples + 64 * 1024 - 1) // (64 * 1024)
        cooldown = max(16, minimum_periods - 1)
        candidate = cls.model_construct(
            request_digest="sha256:" + "0" * 64,
            mode=mode,
            cooldown_periods=cooldown,
        )
        document = candidate.model_dump(mode="json", exclude={"request_digest"})
        return cls.model_validate({**document, "request_digest": canonical_digest(document)})


def gain_controller_policy_digest(policy: GainControllerPolicyV1) -> str:
    return canonical_digest(policy.model_dump(mode="json", exclude={"request_digest"}))


class TandemEventDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"


class TandemGainEventV1(ContractModel):
    """One sample-aligned post-change gain event from the FPGA controller."""

    schema_version: Literal[1] = 1
    sample_sequence: Annotated[int, Field(ge=0)]
    event_sequence: Annotated[int, Field(ge=0)]
    flags: Annotated[int, Field(ge=0, le=0xFFFF)]
    direction: TandemEventDirection
    rx0_gain_index: Annotated[int, Field(ge=0, le=127)]
    rx1_gain_index: Annotated[int, Field(ge=0, le=127)]

    @model_validator(mode="after")
    def _gains_are_tandem(self) -> Self:
        if self.rx0_gain_index != self.rx1_gain_index:
            raise ValueError("tandem gain event must retain equal physical-RX gains")
        return self


class TandemBlockEvidenceV1(ContractModel):
    """Typed tandem ownership, endpoint, and event evidence for one IQ refill."""

    schema_version: Literal[1] = 1
    request_digest: Sha256Digest
    mode: GainControllerMode
    controller_receiver_ids: tuple[Literal[0], Literal[1]] = (0, 1)
    ownership_epoch: Annotated[int, Field(gt=0)]
    tandem_state: Literal["armed_hold", "armed_auto"]
    tandem_fault_flags: Annotated[int, Field(ge=0)]
    tandem_transition_count: Annotated[int, Field(ge=0)]
    gain_table_id: Annotated[int, Field(ge=1)]
    threshold_provenance: Annotated[int, Field(ge=0)]
    minimum_gain_db: Annotated[int, Field(ge=-10, le=100)]
    maximum_gain_db: Annotated[int, Field(ge=-10, le=100)]
    initial_gain_db: Annotated[int, Field(ge=-10, le=100)]
    minimum_gain_index: Annotated[int, Field(ge=0, le=127)]
    maximum_gain_index: Annotated[int, Field(ge=0, le=127)]
    rx0_gain_index: Annotated[int, Field(ge=0, le=127)]
    rx1_gain_index: Annotated[int, Field(ge=0, le=127)]
    ad9361_temperature_mdeg_c: int | None = None
    gain_events: tuple[TandemGainEventV1, ...] = ()

    @model_validator(mode="after")
    def _evidence_is_consistent(self) -> Self:
        expected_state = {
            GainControllerMode.TANDEM_HOLD: "armed_hold",
            GainControllerMode.TANDEM_AUTO: "armed_auto",
        }[self.mode]
        if self.tandem_state != expected_state:
            raise ValueError("tandem state disagrees with requested controller mode")
        if self.rx0_gain_index != self.rx1_gain_index:
            raise ValueError("tandem endpoint gains differ")
        if not self.minimum_gain_db <= self.initial_gain_db <= self.maximum_gain_db:
            raise ValueError("tandem gain request bounds are unordered")
        if not self.minimum_gain_index <= self.rx0_gain_index <= self.maximum_gain_index:
            raise ValueError("tandem endpoint gain lies outside the admitted index range")
        if self.mode is GainControllerMode.TANDEM_HOLD and self.gain_events:
            raise ValueError("tandem HOLD metadata cannot contain gain transitions")
        if (
            tuple(sorted(self.gain_events, key=lambda item: item.sample_sequence))
            != self.gain_events
        ):
            raise ValueError("tandem gain events must be sample ordered")
        return self
