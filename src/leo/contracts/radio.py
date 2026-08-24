"""Versioned radio and per-block metadata contracts."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from leo.contracts.base import ContractModel
from leo.contracts.states import (
    ContinuityStatus,
    GainMode,
    RadioTransport,
    SampleFormat,
    SampleLayout,
    TimingMethod,
)

RadioId = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class ReceiverGainV1(ContractModel):
    schema_version: Literal[1] = 1
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    gain_db: Annotated[float, Field(ge=-10.0, le=100.0)]


class RadioIdentityV1(ContractModel):
    schema_version: Literal[1] = 1
    radio_id: RadioId
    serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    uri: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    transport: RadioTransport
    model: Annotated[str, StringConstraints(min_length=1, max_length=128)] = "Pluto+"
    firmware_version: Annotated[str | None, StringConstraints(min_length=1, max_length=128)] = None
    hardware_revision: Annotated[str | None, StringConstraints(min_length=1, max_length=128)] = None


class RadioCapabilitiesV1(ContractModel):
    schema_version: Literal[1] = 1
    receiver_ids: tuple[Annotated[int, Field(ge=0, le=1)], ...]
    minimum_sample_rate_hz: Annotated[int, Field(gt=0)]
    maximum_sample_rate_hz: Annotated[int, Field(gt=0)]
    supports_device_sample_counter: bool = False
    supports_continuity_sequence: bool = False

    @model_validator(mode="after")
    def _validate_ranges(self) -> Self:
        if not self.receiver_ids or tuple(sorted(set(self.receiver_ids))) != self.receiver_ids:
            raise ValueError("capability receiver IDs must be non-empty, unique, and sorted")
        if self.minimum_sample_rate_hz > self.maximum_sample_rate_hz:
            raise ValueError("minimum sample rate exceeds maximum")
        return self


class RadioSettingsV1(ContractModel):
    schema_version: Literal[1] = 1
    center_frequency_hz: Annotated[int, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    bandwidth_hz: Annotated[int, Field(gt=0)]
    receiver_ids: tuple[Annotated[int, Field(ge=0, le=1)], ...]
    gain_mode: GainMode
    gains: tuple[ReceiverGainV1, ...] = ()

    @field_validator("receiver_ids")
    @classmethod
    def _receivers_are_canonical(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or len(value) > 2 or tuple(sorted(set(value))) != value:
            raise ValueError("receiver IDs must contain one or two unique sorted values")
        return value

    @model_validator(mode="after")
    def _gains_match_receivers(self) -> Self:
        gain_receivers = tuple(gain.receiver_id for gain in self.gains)
        if self.gain_mode is GainMode.MANUAL:
            if gain_receivers != self.receiver_ids:
                raise ValueError("manual settings require gain for each receiver")
        elif self.gains:
            raise ValueError("automatic gain settings must not contain manual gains")
        return self


class NanosecondIntervalV1(ContractModel):
    schema_version: Literal[1] = 1
    lower_ns: Annotated[int, Field(ge=0)]
    upper_ns: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.lower_ns > self.upper_ns:
            raise ValueError("nanosecond interval lower bound exceeds upper bound")
        return self


class IqBlockMetadataV1(ContractModel):
    """Serializable observations for an IQ block; sample bytes live in the domain object."""

    schema_version: Literal[1] = 1
    radio_id: RadioId
    receiver_ids: tuple[Annotated[int, Field(ge=0, le=1)], ...]
    sample_count: Annotated[int, Field(gt=0)]
    session_sample_start: Annotated[int, Field(ge=0)]
    host_request_utc_ns: NanosecondIntervalV1
    host_request_monotonic_ns: NanosecondIntervalV1
    timing_method: TimingMethod = TimingMethod.HOST_BRACKET
    device_sample_counter: Annotated[int, Field(ge=0)] | None = None
    source_sequence: Annotated[int, Field(ge=0)] | None = None
    continuity: ContinuityStatus = ContinuityStatus.UNKNOWN
    missing_samples_before: Annotated[int, Field(ge=0)] = 0
    overflow_observed: bool = False
    hardware_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    sample_format: Literal[SampleFormat.CI16_LE] = SampleFormat.CI16_LE
    sample_layout: Literal[SampleLayout.SAMPLE_RECEIVER_IQ] = SampleLayout.SAMPLE_RECEIVER_IQ

    @field_validator("receiver_ids")
    @classmethod
    def _receivers_are_canonical(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or len(value) > 2 or tuple(sorted(set(value))) != value:
            raise ValueError("block receiver IDs must contain one or two unique sorted values")
        return value

    @model_validator(mode="after")
    def _continuity_fields_agree(self) -> Self:
        if self.continuity is ContinuityStatus.GAP_BEFORE and self.missing_samples_before == 0:
            raise ValueError("gap continuity requires missing_samples_before")
        if self.continuity is not ContinuityStatus.GAP_BEFORE and self.missing_samples_before:
            raise ValueError("missing_samples_before is valid only for a gap")
        if self.continuity is ContinuityStatus.OVERFLOW and not self.overflow_observed:
            raise ValueError("overflow continuity requires overflow_observed")
        return self


class IqBlockMetadataV2(IqBlockMetadataV1):
    """Counter-authoritative metadata atomically bound to one returned IQ refill."""

    schema_version: Literal[2] = 2
    stream_generation: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    metadata_abi_version: Annotated[int, Field(ge=1)]
    metadata_flags: Annotated[int, Field(ge=0)]
    kernel_buffers: Annotated[int, Field(ge=1, le=64)]
    sample_time_realtime_ns: NanosecondIntervalV1 | None = None
    sample_time_monotonic_ns: NanosecondIntervalV1 | None = None
    sample_time_uncertainty_ns: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def _counter_evidence_is_complete(self) -> Self:
        if self.device_sample_counter is None or self.source_sequence is None:
            raise ValueError("V2 IQ metadata requires device counter and source sequence")
        if (self.sample_time_realtime_ns is None) != (self.sample_time_monotonic_ns is None):
            raise ValueError("sample-clock realtime and monotonic bounds must appear together")
        return self


IqBlockMetadataContract = Annotated[
    IqBlockMetadataV1 | IqBlockMetadataV2,
    Field(discriminator="schema_version"),
]
_IQ_BLOCK_METADATA_ADAPTER = TypeAdapter(IqBlockMetadataContract)


def parse_iq_block_metadata_json(payload: bytes | str) -> IqBlockMetadataV1:
    """Decode every supported immutable IQ timeline record."""

    return _IQ_BLOCK_METADATA_ADAPTER.validate_json(payload)
