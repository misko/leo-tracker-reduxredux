"""Durable production policy for paired mixed-native-rate dwells."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.profile import ProfileName, Tag
from leo.contracts.states import StarlinkEdge

MIXED_RATE_SCHEDULE_POLICY_V1 = "mixed-native-rates-16-v1"
MIXED_RATE_10M_SCHEDULE_POLICY_V1 = "mixed-native-rates-16-10m-v1"
MIXED_RATE_SAFE_SCHEDULE_POLICY_V1 = "mixed-native-rates-16-safe-v1"
MIXED_RATE_SCHEDULE_CYCLE_LENGTH = 16

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
