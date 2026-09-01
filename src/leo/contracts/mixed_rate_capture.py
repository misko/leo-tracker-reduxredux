"""Additive capture authority for two radios with unequal native sample rates."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.device_buffer import (
    DIRECT_ASYNC_PROFILE_TAG_V1,
    DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V2,
    DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V3,
    DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V4,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.gain_control import GainControllerPolicyV1
from leo.contracts.mixed_rate_schedule import (
    ProductionDwellClass,
    ProductionDwellClassV2,
    ProductionDwellClassV3,
    ProductionTuningBranchV2,
)
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


class ProductionRadioPlanV2(ContractModel):
    """One exact production-policy leg, including tandem-controller authority."""

    schema_version: Literal[2] = 2
    radio_id: RadioId
    profile_revision: CaptureProfileRevisionV2
    resolved_sample_count: Annotated[int, Field(gt=0)]
    requested_settings: RadioSettingsV1
    gain_controller: GainControllerPolicyV1
    starlink_channel: Annotated[int, Field(ge=1, le=4)]
    starlink_edge: StarlinkEdge
    pilot_if_center_frequency_hz: Annotated[int, Field(gt=0)]
    channel_if_start_hz: Annotated[int, Field(gt=0)]
    channel_if_stop_hz: Annotated[int, Field(gt=0)]
    captured_if_start_hz: Annotated[int, Field(gt=0)]
    captured_if_stop_hz: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _leg_is_exact(self) -> Self:
        profile = self.profile_revision.profile
        if profile.duration_seconds is None or profile.sample_count is not None:
            raise ValueError("production leg requires an exact profile duration")
        expected_count = int(
            (profile.duration_seconds * profile.sample_rate_hz).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )
        if self.resolved_sample_count != expected_count:
            raise ValueError("production leg sample count disagrees with profile duration")
        if (
            self.requested_settings.sample_rate_hz != profile.sample_rate_hz
            or self.requested_settings.bandwidth_hz != profile.bandwidth_hz
            or self.requested_settings.receiver_ids != profile.receivers
        ):
            raise ValueError("production leg requested geometry disagrees with profile")
        if self.requested_settings.gain_mode.value != "manual":
            raise ValueError("tandem-controlled production leg must enter through manual gain")
        if self.requested_settings.gains != profile.gains:
            raise ValueError("production leg seed gain disagrees with profile")
        expected_bounds = starlink_channel_if_bounds_hz(self.starlink_channel)
        expected_pilot = starlink_edge_if_center_frequency_hz(
            self.starlink_channel, self.starlink_edge
        )
        expected_center = starlink_maximum_coverage_if_center_frequency_hz(
            self.starlink_channel,
            self.starlink_edge,
            bandwidth_hz=profile.bandwidth_hz,
        )
        expected_captured = (
            expected_center - profile.bandwidth_hz // 2,
            expected_center + profile.bandwidth_hz // 2,
        )
        if (
            (self.channel_if_start_hz, self.channel_if_stop_hz) != expected_bounds
            or self.pilot_if_center_frequency_hz != expected_pilot
            or self.requested_settings.center_frequency_hz != expected_center
            or (self.captured_if_start_hz, self.captured_if_stop_hz) != expected_captured
            or profile.bandwidth_hz != profile.sample_rate_hz
        ):
            raise ValueError("production leg does not match maximum-coverage native geometry")
        return self


class CapturePlanV4(ContractModel):
    """Additive plan for the exact 8-slot policy and asymmetric receiver geometry."""

    schema_version: Literal[4] = 4
    plan_digest: Sha256Digest
    scheduled_intent_digest: Sha256Digest
    dwell_class: ProductionDwellClassV2
    tuning_branch: ProductionTuningBranchV2
    radio_ids: tuple[RadioId, RadioId]
    radio_plans: tuple[ProductionRadioPlanV2, ProductionRadioPlanV2]
    source_type: SourceType = SourceType.LIVE
    duration_seconds: Annotated[Decimal, Field(gt=0)]
    requested_synchronization_mode: Literal[SynchronizationMode.BEST_EFFORT] = (
        SynchronizationMode.BEST_EFFORT
    )
    effective_synchronization_mode: Literal[SynchronizationMode.BEST_EFFORT] = (
        SynchronizationMode.BEST_EFFORT
    )

    @field_validator("radio_ids")
    @classmethod
    def _v4_radio_ids_are_unique(cls, value: tuple[str, str]) -> tuple[str, str]:
        if len(set(value)) != 2:
            raise ValueError("production plan radio IDs must be unique")
        return value

    @model_validator(mode="after")
    def _plan_is_closed_v4(self) -> Self:
        if tuple(item.radio_id for item in self.radio_plans) != self.radio_ids:
            raise ValueError("production plan leg order must match radio order")
        rates = tuple(item.requested_settings.sample_rate_hz for item in self.radio_plans)
        expected_rates = {
            ProductionDwellClassV2.BOTH_2P5: (2_500_000, 2_500_000),
            ProductionDwellClassV2.BOTH_5: (5_000_000, 5_000_000),
            ProductionDwellClassV2.MIXED_2P5_5: (2_500_000, 5_000_000),
            ProductionDwellClassV2.MIXED_2P5_10: (2_500_000, 10_000_000),
            ProductionDwellClassV2.MIXED_2P5_15: (2_500_000, 15_000_000),
            ProductionDwellClassV2.MIXED_2P5_20: (2_500_000, 20_000_000),
        }[self.dwell_class]
        if sorted(rates) != sorted(expected_rates):
            raise ValueError("production plan rate geometry disagrees with dwell class")
        is_mixed = self.dwell_class.value.startswith("mixed_")
        if is_mixed:
            if self.tuning_branch is not ProductionTuningBranchV2.SAME:
                raise ValueError("mixed production plan requires common tuning")
            targets = {(leg.starlink_channel, leg.starlink_edge) for leg in self.radio_plans}
            if len(targets) != 1:
                raise ValueError("mixed production plan requires one common RF target")
        elif self.tuning_branch is ProductionTuningBranchV2.SAME:
            if len({(leg.starlink_channel, leg.starlink_edge) for leg in self.radio_plans}) != 1:
                raise ValueError("same tuning plan does not use one target")
        elif self.tuning_branch is ProductionTuningBranchV2.SAME_CHANNEL_OPPOSITE_EDGE:
            first, second = self.radio_plans
            if (
                first.starlink_channel != second.starlink_channel
                or first.starlink_edge is second.starlink_edge
            ):
                raise ValueError("opposite-edge tuning plan is invalid")
        for leg in self.radio_plans:
            profile = leg.profile_revision.profile
            expected_receiver_count = (
                1 if is_mixed and leg.requested_settings.sample_rate_hz > 5_000_000 else 2
            )
            if len(leg.requested_settings.receiver_ids) != expected_receiver_count:
                raise ValueError("production plan receiver geometry disagrees with dwell class")
            if profile.duration_seconds != self.duration_seconds:
                raise ValueError("production profiles must use one duration")
            if (
                profile.storage_policy != _DEVICE_AXIS_STORAGE_POLICY_V1
                or profile.continuity_policy is not ContinuityPolicy.ALLOW_SEGMENTS
                or profile.peer_failure_policy is not PeerFailurePolicy.FAIL_SESSION
                or profile.synchronization_mode is not SynchronizationMode.BEST_EFFORT
                or profile.require_device_metadata is not True
            ):
                raise ValueError("production profile integrity policy is incomplete")
        expected_digest = capture_plan_v4_digest(self)
        if self.plan_digest != expected_digest:
            raise ValueError(f"production plan digest does not match content: {expected_digest}")
        return self


def capture_plan_v4_digest(plan: CapturePlanV4) -> str:
    return canonical_digest(plan.model_dump(mode="json", exclude={"plan_digest"}))


class CapturePlanV5(ContractModel):
    """Additive plan for uniform direct-async 2.5 x 10/15/25 MS/s dwells."""

    schema_version: Literal[5] = 5
    plan_digest: Sha256Digest
    scheduled_intent_digest: Sha256Digest
    dwell_class: ProductionDwellClassV3
    tuning_branch: Literal[ProductionTuningBranchV2.SAME] = ProductionTuningBranchV2.SAME
    radio_ids: tuple[RadioId, RadioId]
    radio_plans: tuple[ProductionRadioPlanV2, ProductionRadioPlanV2]
    source_type: SourceType = SourceType.LIVE
    duration_seconds: Annotated[Decimal, Field(gt=0)]
    requested_synchronization_mode: Literal[SynchronizationMode.BEST_EFFORT] = (
        SynchronizationMode.BEST_EFFORT
    )
    effective_synchronization_mode: Literal[SynchronizationMode.BEST_EFFORT] = (
        SynchronizationMode.BEST_EFFORT
    )

    @field_validator("radio_ids")
    @classmethod
    def _v5_radio_ids_are_unique(cls, value: tuple[str, str]) -> tuple[str, str]:
        if len(set(value)) != 2:
            raise ValueError("direct-async production plan radio IDs must be unique")
        return value

    @model_validator(mode="after")
    def _plan_is_closed_v5(self) -> Self:
        if tuple(item.radio_id for item in self.radio_plans) != self.radio_ids:
            raise ValueError("direct-async production plan leg order must match radio order")
        high_rate = {
            ProductionDwellClassV3.MIXED_2P5_10: 10_000_000,
            ProductionDwellClassV3.MIXED_2P5_15: 15_000_000,
            ProductionDwellClassV3.MIXED_2P5_25: 25_000_000,
        }[self.dwell_class]
        if sorted(item.requested_settings.sample_rate_hz for item in self.radio_plans) != [
            2_500_000,
            high_rate,
        ]:
            raise ValueError("direct-async plan rate geometry disagrees with dwell class")
        if len({(leg.starlink_channel, leg.starlink_edge) for leg in self.radio_plans}) != 1:
            raise ValueError("direct-async production plan requires one common RF target")
        for leg in self.radio_plans:
            profile = leg.profile_revision.profile
            high_leg = leg.requested_settings.sample_rate_hz != 2_500_000
            if len(leg.requested_settings.receiver_ids) != (1 if high_leg else 2):
                raise ValueError("direct-async plan receiver geometry is invalid")
            if high_leg and not {
                DIRECT_ASYNC_PROFILE_TAG_V1,
                DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V2,
                DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V3,
                DIRECT_ASYNC_RAM_DROP_PROFILE_TAG_V4,
            }.intersection(profile.tags):
                raise ValueError("direct-async high-rate profile lacks its device-buffer policy")
            if profile.duration_seconds != self.duration_seconds:
                raise ValueError("direct-async production profiles must use one duration")
            if (
                profile.storage_policy != _DEVICE_AXIS_STORAGE_POLICY_V1
                or profile.continuity_policy is not ContinuityPolicy.ALLOW_SEGMENTS
                or profile.peer_failure_policy is not PeerFailurePolicy.FAIL_SESSION
                or profile.synchronization_mode is not SynchronizationMode.BEST_EFFORT
                or profile.require_device_metadata is not True
            ):
                raise ValueError("direct-async production profile integrity policy is incomplete")
        expected_digest = capture_plan_v5_digest(self)
        if self.plan_digest != expected_digest:
            raise ValueError(
                f"direct-async production plan digest does not match content: {expected_digest}"
            )
        return self


def capture_plan_v5_digest(plan: CapturePlanV5) -> str:
    return canonical_digest(plan.model_dump(mode="json", exclude={"plan_digest"}))
