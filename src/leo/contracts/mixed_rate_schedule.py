"""Durable production policy for paired mixed-native-rate dwells."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.gain_control import GainControllerPolicyV1
from leo.contracts.profile import ProfileName, Tag
from leo.contracts.states import StarlinkEdge

MIXED_RATE_SCHEDULE_POLICY_V1 = "mixed-native-rates-16-v1"
MIXED_RATE_10M_SCHEDULE_POLICY_V1 = "mixed-native-rates-16-10m-v1"
MIXED_RATE_SAFE_SCHEDULE_POLICY_V1 = "mixed-native-rates-16-safe-v1"
MIXED_RATE_SCHEDULE_CYCLE_LENGTH = 16
PRODUCTION_NATIVE_RATE_POLICY_V2 = "production-native-rates-8-v2"
PRODUCTION_2P5_10_15_RATE_POLICY_V2 = "production-native-rates-2p5-10-15-8-v2"
PRODUCTION_NATIVE_RATE_CYCLE_LENGTH_V2 = 8
PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3 = "production-direct-async-2p5-10-15-25-6-v3"
PRODUCTION_DIRECT_ASYNC_RATE_CYCLE_LENGTH_V3 = 6

OperationKey = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9:._+-]*$"),
]
RadioId = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class ProductionDwellClass(StrEnum):
    """Closed slot classes in the production mixed-rate policy."""

    ORDINARY_POOL = "ordinary_pool"
    MIXED_2P5_5 = "mixed_2p5_5"
    MIXED_2P5_10 = "mixed_2p5_10"
    MIXED_2P5_15 = "mixed_2p5_15"


class ScheduledRadioRateV1(ContractModel):
    """One radio's immutable rate assignment for a scheduled dwell."""

    schema_version: Literal[1] = 1
    radio_id: RadioId
    sample_rate_hz: Literal[2_500_000, 5_000_000, 10_000_000, 15_000_000]
    profile_name: ProfileName
    profile_revision_digest: Sha256Digest


class ProductionDwellIntentV1(ContractModel):
    """Fully resolved dwell intent persisted before acquisition admission."""

    schema_version: Literal[1] = 1
    intent_digest: Sha256Digest
    policy_id: Literal[
        "mixed-native-rates-16-v1",
        "mixed-native-rates-16-10m-v1",
        "mixed-native-rates-16-safe-v1",
    ] = "mixed-native-rates-16-v1"
    operation_key: OperationKey
    cadence_ordinal: Annotated[int, Field(ge=0)]
    cycle_index: Annotated[int, Field(ge=0)]
    cycle_slot: Annotated[int, Field(ge=0, lt=MIXED_RATE_SCHEDULE_CYCLE_LENGTH)]
    dwell_class: ProductionDwellClass
    ordinary_profile_name: ProfileName | None = None
    ordinary_profile_names: tuple[ProfileName, ...] = ()
    radio_ids: tuple[RadioId, RadioId]
    starlink_channel: Annotated[int, Field(ge=1, le=4)] | None = None
    starlink_edge: StarlinkEdge | None = None
    radio_rates: tuple[ScheduledRadioRateV1, ...] = ()
    extra_tags: tuple[Tag, ...] = ()

    @field_validator("ordinary_profile_names")
    @classmethod
    def _ordinary_profiles_are_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(set(value)) != len(value):
            raise ValueError("ordinary profile pool must be non-empty and unique")
        return value

    @field_validator("extra_tags")
    @classmethod
    def _tags_are_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("scheduled dwell tags must be unique and sorted")
        return value

    @model_validator(mode="after")
    def _intent_is_closed(self) -> Self:
        if len(set(self.radio_ids)) != 2:
            raise ValueError("production dwell intent requires two unique radios")
        if self.cycle_index != self.cadence_ordinal // MIXED_RATE_SCHEDULE_CYCLE_LENGTH:
            raise ValueError("cycle index disagrees with cadence ordinal")
        if self.cycle_slot != self.cadence_ordinal % MIXED_RATE_SCHEDULE_CYCLE_LENGTH:
            raise ValueError("cycle slot disagrees with cadence ordinal")
        if self.dwell_class is ProductionDwellClass.ORDINARY_POOL:
            if self.ordinary_profile_name not in self.ordinary_profile_names:
                raise ValueError("ordinary dwell selection is outside its profile pool")
            if self.starlink_channel is not None or self.starlink_edge is not None:
                raise ValueError("ordinary dwell leaves tuning to its selected profile policy")
            if self.radio_rates:
                raise ValueError("ordinary dwell must not carry mixed radio rates")
        else:
            if self.policy_id == MIXED_RATE_SAFE_SCHEDULE_POLICY_V1 and self.dwell_class in {
                ProductionDwellClass.MIXED_2P5_10,
                ProductionDwellClass.MIXED_2P5_15,
            }:
                raise ValueError("safe mixed-rate policy cannot schedule an unqualified high leg")
            if self.ordinary_profile_name is not None:
                raise ValueError("mixed dwell must not select one ordinary profile")
            if self.starlink_channel is None or self.starlink_edge is None:
                raise ValueError("mixed dwell requires one common Starlink channel and edge")
            if len(self.radio_rates) != 2:
                raise ValueError("mixed dwell requires exactly two radio-rate assignments")
            radio_ids = tuple(item.radio_id for item in self.radio_rates)
            if radio_ids != self.radio_ids:
                raise ValueError("mixed dwell rate assignments must match radio order")
            expected_rates = {
                ProductionDwellClass.MIXED_2P5_5: {2_500_000, 5_000_000},
                ProductionDwellClass.MIXED_2P5_10: {2_500_000, 10_000_000},
                ProductionDwellClass.MIXED_2P5_15: {2_500_000, 15_000_000},
            }[self.dwell_class]
            if {item.sample_rate_hz for item in self.radio_rates} != expected_rates:
                raise ValueError("mixed dwell rate pair disagrees with its class")
        expected_digest = production_dwell_intent_digest(self)
        if self.intent_digest != expected_digest:
            raise ValueError(
                f"scheduled dwell intent digest does not match content: {expected_digest}"
            )
        return self


def production_dwell_intent_digest(intent: ProductionDwellIntentV1) -> str:
    """Address one resolved schedule decision without its self digest."""

    return canonical_digest(intent.model_dump(mode="json", exclude={"intent_digest"}))


class ProductionDwellClassV2(StrEnum):
    """Exact slot classes in the production 8-dwell native-rate policy."""

    BOTH_2P5 = "both_2p5"
    BOTH_5 = "both_5"
    MIXED_2P5_5 = "mixed_2p5_5"
    MIXED_2P5_10 = "mixed_2p5_10"
    MIXED_2P5_15 = "mixed_2p5_15"
    MIXED_2P5_20 = "mixed_2p5_20"


class ProductionTuningBranchV2(StrEnum):
    SAME = "same"
    SAME_CHANNEL_OPPOSITE_EDGE = "same_channel_opposite_edge"
    INDEPENDENT = "independent"


class ScheduledRadioLegV2(ContractModel):
    """One radio's fully resolved profile, tuning, receiver, and controller authority."""

    schema_version: Literal[2] = 2
    radio_id: RadioId
    sample_rate_hz: Literal[2_500_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000]
    receiver_ids: tuple[Literal[0, 1], ...]
    profile_name: ProfileName
    profile_revision_digest: Sha256Digest
    starlink_channel: Annotated[int, Field(ge=1, le=4)]
    starlink_edge: StarlinkEdge
    gain_controller: GainControllerPolicyV1

    @field_validator("receiver_ids")
    @classmethod
    def _receivers_are_canonical(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value not in {(0,), (1,), (0, 1)}:
            raise ValueError("scheduled receiver selection is not canonical")
        return value


class ProductionDwellIntentV2(ContractModel):
    """Complete durable intent for one slot of the production 8-dwell policy."""

    schema_version: Literal[2] = 2
    intent_digest: Sha256Digest
    policy_id: Literal[
        "production-native-rates-8-v2",
        "production-native-rates-2p5-10-15-8-v2",
    ] = "production-native-rates-8-v2"
    operation_key: OperationKey
    cadence_ordinal: Annotated[int, Field(ge=0)]
    cycle_index: Annotated[int, Field(ge=0)]
    cycle_slot: Annotated[int, Field(ge=0, lt=PRODUCTION_NATIVE_RATE_CYCLE_LENGTH_V2)]
    dwell_class: ProductionDwellClassV2
    tuning_branch: ProductionTuningBranchV2
    radio_ids: tuple[RadioId, RadioId]
    radio_legs: tuple[ScheduledRadioLegV2, ScheduledRadioLegV2]
    extra_tags: tuple[Tag, ...] = ()

    @field_validator("extra_tags")
    @classmethod
    def _v2_tags_are_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("scheduled dwell tags must be unique and sorted")
        return value

    @model_validator(mode="after")
    def _intent_is_closed_v2(self) -> Self:
        if len(set(self.radio_ids)) != 2:
            raise ValueError("production dwell intent requires two unique radios")
        if self.cycle_index != self.cadence_ordinal // PRODUCTION_NATIVE_RATE_CYCLE_LENGTH_V2:
            raise ValueError("cycle index disagrees with cadence ordinal")
        if self.cycle_slot != self.cadence_ordinal % PRODUCTION_NATIVE_RATE_CYCLE_LENGTH_V2:
            raise ValueError("cycle slot disagrees with cadence ordinal")
        if tuple(item.radio_id for item in self.radio_legs) != self.radio_ids:
            raise ValueError("scheduled radio legs must match configured radio order")
        rates = tuple(item.sample_rate_hz for item in self.radio_legs)
        expected_rates = {
            ProductionDwellClassV2.BOTH_2P5: (2_500_000, 2_500_000),
            ProductionDwellClassV2.BOTH_5: (5_000_000, 5_000_000),
            ProductionDwellClassV2.MIXED_2P5_5: (2_500_000, 5_000_000),
            ProductionDwellClassV2.MIXED_2P5_10: (2_500_000, 10_000_000),
            ProductionDwellClassV2.MIXED_2P5_15: (2_500_000, 15_000_000),
            ProductionDwellClassV2.MIXED_2P5_20: (2_500_000, 20_000_000),
        }[self.dwell_class]
        if sorted(rates) != sorted(expected_rates):
            raise ValueError("scheduled rate geometry disagrees with dwell class")
        is_mixed = self.dwell_class.value.startswith("mixed_")
        if is_mixed:
            if self.tuning_branch is not ProductionTuningBranchV2.SAME:
                raise ValueError("mixed-rate dwell requires common tuning")
            targets = {(item.starlink_channel, item.starlink_edge) for item in self.radio_legs}
            if len(targets) != 1:
                raise ValueError("mixed-rate radio legs must use one common target")
        elif self.tuning_branch is ProductionTuningBranchV2.SAME:
            if len({(item.starlink_channel, item.starlink_edge) for item in self.radio_legs}) != 1:
                raise ValueError("same tuning branch requires one common target")
        elif self.tuning_branch is ProductionTuningBranchV2.SAME_CHANNEL_OPPOSITE_EDGE:
            first, second = self.radio_legs
            if (
                first.starlink_channel != second.starlink_channel
                or first.starlink_edge is second.starlink_edge
            ):
                raise ValueError("opposite-edge branch geometry is invalid")
        for leg in self.radio_legs:
            high_single = is_mixed and leg.sample_rate_hz > 5_000_000
            expected_receivers = 1 if high_single else 2
            if len(leg.receiver_ids) != expected_receivers:
                raise ValueError("scheduled receiver geometry disagrees with rate class")
        expected_digest = production_dwell_intent_v2_digest(self)
        if self.intent_digest != expected_digest:
            raise ValueError(
                f"scheduled V2 dwell intent digest does not match content: {expected_digest}"
            )
        return self


def production_dwell_intent_v2_digest(intent: ProductionDwellIntentV2) -> str:
    return canonical_digest(intent.model_dump(mode="json", exclude={"intent_digest"}))


class ProductionDwellClassV3(StrEnum):
    """Exact mixed-rate classes qualified for direct-async firmware RC1."""

    MIXED_2P5_10 = "mixed_2p5_10"
    MIXED_2P5_15 = "mixed_2p5_15"
    MIXED_2P5_25 = "mixed_2p5_25"


class ScheduledRadioLegV3(ContractModel):
    """One resolved leg in the direct-async production policy."""

    schema_version: Literal[3] = 3
    radio_id: RadioId
    sample_rate_hz: Literal[2_500_000, 10_000_000, 15_000_000, 25_000_000]
    receiver_ids: tuple[Literal[0, 1], ...]
    profile_name: ProfileName
    profile_revision_digest: Sha256Digest
    starlink_channel: Annotated[int, Field(ge=1, le=4)]
    starlink_edge: StarlinkEdge
    gain_controller: GainControllerPolicyV1

    @field_validator("receiver_ids")
    @classmethod
    def _receivers_are_canonical_v3(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value not in {(0,), (1,), (0, 1)}:
            raise ValueError("scheduled receiver selection is not canonical")
        return value


class ProductionDwellIntentV3(ContractModel):
    """Durable authority for uniform 2.5 x 10/15/25 MS/s same-target dwells."""

    schema_version: Literal[3] = 3
    intent_digest: Sha256Digest
    policy_id: Literal["production-direct-async-2p5-10-15-25-6-v3"] = (
        "production-direct-async-2p5-10-15-25-6-v3"
    )
    operation_key: OperationKey
    cadence_ordinal: Annotated[int, Field(ge=0)]
    cycle_index: Annotated[int, Field(ge=0)]
    cycle_slot: Annotated[int, Field(ge=0, lt=PRODUCTION_DIRECT_ASYNC_RATE_CYCLE_LENGTH_V3)]
    dwell_class: ProductionDwellClassV3
    tuning_branch: Literal[ProductionTuningBranchV2.SAME] = ProductionTuningBranchV2.SAME
    radio_ids: tuple[RadioId, RadioId]
    radio_legs: tuple[ScheduledRadioLegV3, ScheduledRadioLegV3]
    extra_tags: tuple[Tag, ...] = ()

    @field_validator("extra_tags")
    @classmethod
    def _v3_tags_are_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("scheduled dwell tags must be unique and sorted")
        return value

    @model_validator(mode="after")
    def _intent_is_closed_v3(self) -> Self:
        if len(set(self.radio_ids)) != 2:
            raise ValueError("direct-async dwell intent requires two unique radios")
        if self.cycle_index != self.cadence_ordinal // PRODUCTION_DIRECT_ASYNC_RATE_CYCLE_LENGTH_V3:
            raise ValueError("cycle index disagrees with cadence ordinal")
        if self.cycle_slot != self.cadence_ordinal % PRODUCTION_DIRECT_ASYNC_RATE_CYCLE_LENGTH_V3:
            raise ValueError("cycle slot disagrees with cadence ordinal")
        if tuple(item.radio_id for item in self.radio_legs) != self.radio_ids:
            raise ValueError("scheduled radio legs must match configured radio order")
        high_rate = {
            ProductionDwellClassV3.MIXED_2P5_10: 10_000_000,
            ProductionDwellClassV3.MIXED_2P5_15: 15_000_000,
            ProductionDwellClassV3.MIXED_2P5_25: 25_000_000,
        }[self.dwell_class]
        if sorted(item.sample_rate_hz for item in self.radio_legs) != [2_500_000, high_rate]:
            raise ValueError("scheduled rate geometry disagrees with direct-async dwell class")
        if len({(item.starlink_channel, item.starlink_edge) for item in self.radio_legs}) != 1:
            raise ValueError("direct-async mixed-rate legs must use one common target")
        for leg in self.radio_legs:
            expected_receivers = 2 if leg.sample_rate_hz == 2_500_000 else 1
            if len(leg.receiver_ids) != expected_receivers:
                raise ValueError("scheduled receiver geometry disagrees with direct-async policy")
        expected_digest = production_dwell_intent_v3_digest(self)
        if self.intent_digest != expected_digest:
            raise ValueError(
                f"scheduled V3 dwell intent digest does not match content: {expected_digest}"
            )
        return self


def production_dwell_intent_v3_digest(intent: ProductionDwellIntentV3) -> str:
    return canonical_digest(intent.model_dump(mode="json", exclude={"intent_digest"}))
