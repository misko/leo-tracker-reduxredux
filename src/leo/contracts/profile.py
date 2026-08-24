"""Versioned capture-profile and compiled-plan contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.states import (
    ContinuityPolicy,
    GainMode,
    PeerFailurePolicy,
    SourceType,
    StarlinkEdge,
    SynchronizationMode,
)

ProfileName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=96, pattern=r"^[a-z0-9][a-z0-9._-]*$"),
]
Tag = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class CaptureProfileV1(ContractModel):
    """Human-editable signal and acquisition settings before radio selection."""

    schema_version: Literal[1] = 1
    name: ProfileName
    description: Annotated[str | None, StringConstraints(max_length=512)] = None
    center_frequency_hz: Annotated[int, Field(gt=0)]
    rf_center_frequency_hz: Annotated[int, Field(gt=0)] | None = None
    lnb_lo_hz: Annotated[int, Field(ge=0)] | None = None
    starlink_channel: Annotated[str | None, StringConstraints(min_length=1, max_length=64)] = None
    starlink_edge: StarlinkEdge | None = None
    sample_rate_hz: Annotated[int, Field(gt=0)]
    bandwidth_hz: Annotated[int, Field(gt=0)]
    receivers: tuple[Annotated[int, Field(ge=0, le=1)], ...] = (0, 1)
    gain_mode: GainMode = GainMode.MANUAL
    gains: tuple[ReceiverGainV1, ...] = ()
    duration_seconds: Annotated[Decimal, Field(gt=0)] | None = None
    sample_count: Annotated[int, Field(gt=0)] | None = None
    refill_samples: Annotated[int, Field(gt=0)] = 262_144
    settle_seconds: Annotated[Decimal, Field(ge=0)] = Decimal("0.5")
    prime_refills: Annotated[int, Field(ge=0, le=32)] = 1
    continuity_policy: ContinuityPolicy = ContinuityPolicy.REQUIRE_CONTIGUOUS
    synchronization_mode: SynchronizationMode = SynchronizationMode.BEST_EFFORT
    peer_failure_policy: PeerFailurePolicy = PeerFailurePolicy.KEEP_SURVIVOR
    storage_policy: Annotated[
        str,
        StringConstraints(min_length=1, max_length=96, pattern=r"^[a-z0-9][a-z0-9._-]*$"),
    ] = "zstd-128m-v1"
    campaign: Annotated[str | None, StringConstraints(min_length=1, max_length=96)] = None
    tags: tuple[Tag, ...] = ()

    @field_validator("receivers")
    @classmethod
    def _receivers_are_canonical(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or len(value) > 2:
            raise ValueError("a profile must select one or two receivers")
        if tuple(sorted(set(value))) != value:
            raise ValueError("receivers must be unique and sorted")
        return value

    @field_validator("tags")
    @classmethod
    def _tags_are_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("tags must be unique and sorted")
        return value

    @model_validator(mode="after")
    def _validate_duration_and_gain(self) -> Self:
        if (self.duration_seconds is None) == (self.sample_count is None):
            raise ValueError("exactly one of duration_seconds and sample_count is required")
        gain_receivers = tuple(gain.receiver_id for gain in self.gains)
        if self.gain_mode is GainMode.MANUAL:
            if gain_receivers != self.receivers:
                raise ValueError("manual gain requires one ordered gain for every receiver")
        elif self.gains:
            raise ValueError("automatic gain modes must not specify manual gains")
        if (self.starlink_channel is None) != (self.starlink_edge is None):
            raise ValueError("Starlink channel and edge intent must appear together")
        if self.rf_center_frequency_hz is not None and self.lnb_lo_hz is not None:
            expected_rf_center = self.center_frequency_hz + self.lnb_lo_hz
            if self.rf_center_frequency_hz != expected_rf_center:
                raise ValueError("RF center must equal IF center plus LNB LO")
        return self


class CaptureProfileV2(CaptureProfileV1):
    """Live capture settings with an explicit, attested receive-buffer policy."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    kernel_buffers: Annotated[int, Field(ge=2, le=64)] = 8
    refill_queue_capacity: Annotated[int, Field(ge=1, le=256)] = 32
    require_device_metadata: Literal[True] = True


class CaptureProfileRevisionV1(ContractModel):
    """Immutable normalized profile content addressed by its canonical digest."""

    schema_version: Literal[1] = 1
    revision_digest: Sha256Digest
    profile: CaptureProfileV1

    @model_validator(mode="after")
    def _digest_matches_profile(self) -> Self:
        expected = profile_revision_digest(self.profile)
        if self.revision_digest != expected:
            raise ValueError(f"profile revision digest does not match content: {expected}")
        return self

    @classmethod
    def from_profile(cls, profile: CaptureProfileV1) -> CaptureProfileRevisionV1:
        return cls(revision_digest=profile_revision_digest(profile), profile=profile)


class CapturePlanV1(ContractModel):
    """Runtime-independent acquisition plan after selecting one or two radios."""

    schema_version: Literal[1] = 1
    plan_digest: Sha256Digest
    profile_revision: CaptureProfileRevisionV1
    radio_ids: tuple[Annotated[str, StringConstraints(min_length=1, max_length=128)], ...]
    source_type: SourceType = SourceType.LIVE
    resolved_sample_count: Annotated[int, Field(gt=0)]
    requested_synchronization_mode: SynchronizationMode
    effective_synchronization_mode: SynchronizationMode

    @field_validator("radio_ids")
    @classmethod
    def _radios_are_valid(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not 1 <= len(value) <= 2:
            raise ValueError("a capture plan requires one or two radios")
        if len(set(value)) != len(value):
            raise ValueError("capture-plan radio IDs must be unique")
        return value

    @model_validator(mode="after")
    def _plan_is_consistent(self) -> Self:
        expected_mode = (
            self.requested_synchronization_mode
            if len(self.radio_ids) == 2
            else SynchronizationMode.NONE
        )
        if self.effective_synchronization_mode is not expected_mode:
            raise ValueError("effective synchronization mode is inconsistent with radio count")
        expected_digest = capture_plan_digest(self)
        if self.plan_digest != expected_digest:
            raise ValueError(f"capture plan digest does not match content: {expected_digest}")
        return self


class CaptureProfileRevisionV2(ContractModel):
    """Immutable V2 capture profile addressed by its complete normalized content."""

    schema_version: Literal[2] = 2
    revision_digest: Sha256Digest
    profile: CaptureProfileV2

    @model_validator(mode="after")
    def _digest_matches_profile(self) -> Self:
        expected = profile_revision_digest(self.profile)
        if self.revision_digest != expected:
            raise ValueError(f"profile revision digest does not match content: {expected}")
        return self

    @classmethod
    def from_profile(cls, profile: CaptureProfileV2) -> CaptureProfileRevisionV2:
        return cls(revision_digest=profile_revision_digest(profile), profile=profile)


class CapturePlanV2(CapturePlanV1):
    """Live plan whose persisted content includes receive-buffer integrity controls."""

    schema_version: Literal[2] = 2  # type: ignore[assignment]
    profile_revision: CaptureProfileRevisionV2  # type: ignore[assignment]


def profile_revision_digest(profile: CaptureProfileV1 | CaptureProfileV2) -> str:
    return canonical_digest(profile.model_dump(mode="json"))


def capture_plan_digest(plan: CapturePlanV1 | CapturePlanV2) -> str:
    return canonical_digest(plan.model_dump(mode="json", exclude={"plan_digest"}))
