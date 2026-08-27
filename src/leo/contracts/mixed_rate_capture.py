"""Additive capture authority for two radios with unequal native sample rates."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.mixed_rate_schedule import ProductionDwellClass
from leo.contracts.profile import CaptureProfileRevisionV2
from leo.contracts.radio import RadioSettingsV1
from leo.contracts.starlink_frequency import (
    starlink_channel_if_bounds_hz,
    starlink_edge_if_center_frequency_hz,
    starlink_maximum_coverage_if_center_frequency_hz,
)
from leo.contracts.states import (
    ContinuityPolicy,
    PeerFailurePolicy,
    SourceType,
    StarlinkEdge,
    SynchronizationMode,
)

RadioId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
_DEVICE_AXIS_STORAGE_POLICY_V1 = "zstd-128m-device-axis-zero-v1"


class MixedRateRadioPlanV1(ContractModel):
    """One exact profile, endpoint, and requested setting set for one radio."""

    schema_version: Literal[1] = 1
    radio_id: RadioId
    profile_revision: CaptureProfileRevisionV2
    resolved_sample_count: Annotated[int, Field(gt=0)]
    requested_settings: RadioSettingsV1
    pilot_if_center_frequency_hz: Annotated[int, Field(gt=0)]
    channel_if_start_hz: Annotated[int, Field(gt=0)]
    channel_if_stop_hz: Annotated[int, Field(gt=0)]
    captured_if_start_hz: Annotated[int, Field(gt=0)]
    captured_if_stop_hz: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _leg_matches_profile(self) -> Self:
        profile = self.profile_revision.profile
        if profile.duration_seconds is None or profile.sample_count is not None:
            raise ValueError("mixed-rate leg requires an exact profile duration")
        expected_count = int(
            (profile.duration_seconds * profile.sample_rate_hz).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )
        if self.resolved_sample_count != expected_count:
            raise ValueError("mixed-rate leg sample count disagrees with profile duration")
        if self.requested_settings.sample_rate_hz != profile.sample_rate_hz:
            raise ValueError("mixed-rate leg requested rate disagrees with profile")
        if self.requested_settings.bandwidth_hz != profile.bandwidth_hz:
            raise ValueError("mixed-rate leg requested bandwidth disagrees with profile")
        if self.requested_settings.receiver_ids != profile.receivers:
            raise ValueError("mixed-rate leg receiver geometry disagrees with profile")
        if (
            self.requested_settings.gain_mode is not profile.gain_mode
            or self.requested_settings.gains != profile.gains
        ):
            raise ValueError("mixed-rate leg gain settings disagree with profile")
        if self.channel_if_start_hz >= self.channel_if_stop_hz:
            raise ValueError("mixed-rate channel IF bounds are invalid")
        if self.captured_if_start_hz >= self.captured_if_stop_hz:
            raise ValueError("mixed-rate captured IF bounds are invalid")
        if (
            self.captured_if_start_hz < self.channel_if_start_hz
            or self.captured_if_stop_hz > self.channel_if_stop_hz
            or self.captured_if_stop_hz - self.captured_if_start_hz != profile.bandwidth_hz
            or self.requested_settings.center_frequency_hz * 2
            != self.captured_if_start_hz + self.captured_if_stop_hz
            or not (
                self.captured_if_start_hz
                <= self.pilot_if_center_frequency_hz
                <= self.captured_if_stop_hz
            )
            or profile.bandwidth_hz != profile.sample_rate_hz
        ):
            raise ValueError("mixed-rate leg does not maximize in-channel native-rate coverage")
        return self


class CapturePlanV3(ContractModel):
    """Runtime-independent paired plan with one exact geometry per radio."""

    schema_version: Literal[3] = 3
    plan_digest: Sha256Digest
    dwell_class: Literal[
        ProductionDwellClass.MIXED_2P5_5,
        ProductionDwellClass.MIXED_2P5_10,
        ProductionDwellClass.MIXED_2P5_15,
    ]
    radio_ids: tuple[RadioId, RadioId]
    radio_plans: tuple[MixedRateRadioPlanV1, MixedRateRadioPlanV1]
    source_type: SourceType = SourceType.LIVE
    duration_seconds: Annotated[Decimal, Field(gt=0)]
    starlink_channel: Annotated[int, Field(ge=1, le=4)]
    starlink_edge: StarlinkEdge
    requested_synchronization_mode: Literal[SynchronizationMode.BEST_EFFORT] = (
        SynchronizationMode.BEST_EFFORT
    )
    effective_synchronization_mode: Literal[SynchronizationMode.BEST_EFFORT] = (
        SynchronizationMode.BEST_EFFORT
    )

    @field_validator("radio_ids")
    @classmethod
    def _radio_ids_are_unique(cls, value: tuple[str, str]) -> tuple[str, str]:
        if len(set(value)) != 2:
            raise ValueError("mixed-rate plan radio IDs must be unique")
        return value

    @model_validator(mode="after")
    def _plan_is_closed(self) -> Self:
        if tuple(item.radio_id for item in self.radio_plans) != self.radio_ids:
            raise ValueError("mixed-rate leg order must match radio order")
        rates = {item.requested_settings.sample_rate_hz for item in self.radio_plans}
        expected_rates = {
            ProductionDwellClass.MIXED_2P5_5: {2_500_000, 5_000_000},
            ProductionDwellClass.MIXED_2P5_10: {2_500_000, 10_000_000},
            ProductionDwellClass.MIXED_2P5_15: {2_500_000, 15_000_000},
        }[self.dwell_class]
        if rates != expected_rates:
            raise ValueError("mixed-rate plan geometry disagrees with dwell class")
        first_profile = self.radio_plans[0].profile_revision.profile
        for leg in self.radio_plans:
            profile = leg.profile_revision.profile
            expected_channel_bounds = starlink_channel_if_bounds_hz(self.starlink_channel)
            expected_pilot_hz = starlink_edge_if_center_frequency_hz(
                self.starlink_channel,
                self.starlink_edge,
            )
            expected_center_hz = starlink_maximum_coverage_if_center_frequency_hz(
                self.starlink_channel,
                self.starlink_edge,
                bandwidth_hz=profile.bandwidth_hz,
            )
            expected_captured_bounds = (
                expected_center_hz - profile.bandwidth_hz // 2,
                expected_center_hz + profile.bandwidth_hz // 2,
            )
            if (
                (leg.channel_if_start_hz, leg.channel_if_stop_hz) != expected_channel_bounds
                or leg.pilot_if_center_frequency_hz != expected_pilot_hz
                or leg.requested_settings.center_frequency_hz != expected_center_hz
                or (leg.captured_if_start_hz, leg.captured_if_stop_hz) != expected_captured_bounds
            ):
                raise ValueError(
                    "mixed-rate leg does not match the exact maximum-coverage Starlink geometry"
                )
            if profile.duration_seconds != self.duration_seconds:
                raise ValueError("mixed-rate profile durations must match")
            if profile.storage_policy != _DEVICE_AXIS_STORAGE_POLICY_V1:
                raise ValueError("mixed-rate capture requires device-axis-zero storage")
            if profile.continuity_policy is not ContinuityPolicy.ALLOW_SEGMENTS:
                raise ValueError("mixed-rate capture requires segment-aware continuity")
            if profile.peer_failure_policy is not PeerFailurePolicy.FAIL_SESSION:
                raise ValueError("mixed-rate capture requires fail-session peer semantics")
            if profile.synchronization_mode is not SynchronizationMode.BEST_EFFORT:
                raise ValueError("mixed-rate capture requires best-effort synchronization")
            if (
                profile.receivers != first_profile.receivers
                or profile.refill_samples != first_profile.refill_samples
                or profile.kernel_buffers != first_profile.kernel_buffers
                or profile.refill_queue_capacity != first_profile.refill_queue_capacity
                or profile.require_device_metadata is not True
            ):
                raise ValueError("mixed-rate profiles disagree on capture integrity geometry")
        expected_digest = capture_plan_v3_digest(self)
        if self.plan_digest != expected_digest:
            raise ValueError(f"mixed-rate plan digest does not match content: {expected_digest}")
        return self


def capture_plan_v3_digest(plan: CapturePlanV3) -> str:
    return canonical_digest(plan.model_dump(mode="json", exclude={"plan_digest"}))
