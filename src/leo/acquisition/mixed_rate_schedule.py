"""Pure deterministic compiler for the production 16-dwell rate policy."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from leo.contracts.digests import canonical_digest
from leo.contracts.mixed_rate_schedule import (
    MIXED_RATE_10M_SCHEDULE_POLICY_V1,
    MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
    MIXED_RATE_SCHEDULE_CYCLE_LENGTH,
    MIXED_RATE_SCHEDULE_POLICY_V1,
    ProductionDwellClass,
    ProductionDwellIntentV1,
    ScheduledRadioRateV1,
)
from leo.contracts.states import StarlinkEdge

_CYCLE_CLASSES = (
    *(ProductionDwellClass.MIXED_2P5_5 for _ in range(6)),
    *(ProductionDwellClass.MIXED_2P5_15 for _ in range(2)),
    *(ProductionDwellClass.ORDINARY_POOL for _ in range(8)),
)
_SAFE_CYCLE_CLASSES = (
    *(ProductionDwellClass.MIXED_2P5_5 for _ in range(6)),
    *(ProductionDwellClass.ORDINARY_POOL for _ in range(10)),
)
_TEN_M_CYCLE_CLASSES = (
    *(ProductionDwellClass.MIXED_2P5_5 for _ in range(6)),
    *(ProductionDwellClass.MIXED_2P5_10 for _ in range(2)),
    *(ProductionDwellClass.ORDINARY_POOL for _ in range(8)),
)


def compile_production_dwell_intent_v1(
    *,
    operation_key: str,
    cadence_ordinal: int,
    ordinary_profile_names: Sequence[str],
    radio_ids: Sequence[str],
    rate_profile_authority: Mapping[int, tuple[str, str]],
    policy_id: str = MIXED_RATE_SCHEDULE_POLICY_V1,
    extra_tags: Sequence[str] = (),
) -> ProductionDwellIntentV1:
    """Resolve one cadence slot without mutable state or runtime randomness."""

    if cadence_ordinal < 0:
        raise ValueError("cadence ordinal cannot be negative")
    profiles = tuple(ordinary_profile_names)
    radios = tuple(radio_ids)
    if not profiles or len(set(profiles)) != len(profiles):
        raise ValueError("ordinary profile pool must be non-empty and unique")
    if len(radios) != 2 or len(set(radios)) != 2:
        raise ValueError("mixed-rate production policy requires two unique radios")
    required_rates = {
        MIXED_RATE_SAFE_SCHEDULE_POLICY_V1: {2_500_000, 5_000_000},
        MIXED_RATE_10M_SCHEDULE_POLICY_V1: {2_500_000, 5_000_000, 10_000_000},
        MIXED_RATE_SCHEDULE_POLICY_V1: {2_500_000, 5_000_000, 15_000_000},
    }.get(policy_id)
    if policy_id not in {
        MIXED_RATE_SCHEDULE_POLICY_V1,
        MIXED_RATE_10M_SCHEDULE_POLICY_V1,
        MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
    }:
        raise ValueError("mixed-rate schedule policy is unsupported")
    assert required_rates is not None
    if not required_rates.issubset(rate_profile_authority):
        raise ValueError("mixed-rate profile authority omits a scheduled rate")
    tags = tuple(sorted(set(extra_tags)))
    cycle_index, cycle_slot = divmod(cadence_ordinal, MIXED_RATE_SCHEDULE_CYCLE_LENGTH)
    cycle = _cycle_for(cycle_index, profiles, radios, policy_id)
    dwell_class = cycle[cycle_slot]

    common: dict[str, Any] = dict(
        policy_id=policy_id,
        operation_key=operation_key,
        cadence_ordinal=cadence_ordinal,
        cycle_index=cycle_index,
        cycle_slot=cycle_slot,
        dwell_class=dwell_class,
        ordinary_profile_names=profiles,
        radio_ids=radios,
        extra_tags=tags,
    )
    if dwell_class is ProductionDwellClass.ORDINARY_POOL:
        values: dict[str, Any] = {
            **common,
            "ordinary_profile_name": profiles[
                _unbiased_index(
                    len(profiles), domain="ordinary-profile", operation_key=operation_key
                )
            ],
        }
    else:
        high_rate: Literal[5_000_000, 10_000_000, 15_000_000]
        if dwell_class is ProductionDwellClass.MIXED_2P5_5:
            high_rate = 5_000_000
        elif dwell_class is ProductionDwellClass.MIXED_2P5_10:
            high_rate = 10_000_000
        else:
            high_rate = 15_000_000
        high_radio_index = _balanced_high_radio_index(
            cycle=cycle,
            cycle_slot=cycle_slot,
            dwell_class=dwell_class,
            cycle_index=cycle_index,
        )
        rates: list[Literal[2_500_000, 5_000_000, 10_000_000, 15_000_000]] = [
            2_500_000,
            2_500_000,
        ]
        rates[high_radio_index] = high_rate
        values = {
            **common,
            "starlink_channel": 1
            + _unbiased_index(4, domain="channel", operation_key=operation_key),
            "starlink_edge": (
                StarlinkEdge.LOWER
                if _unbiased_index(2, domain="edge", operation_key=operation_key) == 0
                else StarlinkEdge.UPPER
            ),
            "radio_rates": tuple(
                ScheduledRadioRateV1(
                    radio_id=radio_id,
                    sample_rate_hz=rate,
                    profile_name=rate_profile_authority[rate][0],
                    profile_revision_digest=rate_profile_authority[rate][1],
                )
                for radio_id, rate in zip(radios, rates, strict=True)
            ),
        }
    candidate = ProductionDwellIntentV1.model_construct(
        intent_digest="sha256:" + "0" * 64,
        **values,
    )
    document = candidate.model_dump(mode="json", exclude={"intent_digest"})
    return ProductionDwellIntentV1.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
    )


def production_cycle_classes_v1(
    *,
    cycle_index: int,
    ordinary_profile_names: Sequence[str],
    radio_ids: Sequence[str],
    policy_id: str = MIXED_RATE_SCHEDULE_POLICY_V1,
) -> tuple[ProductionDwellClass, ...]:
    """Expose the auditable resolved class permutation for tests and operators."""

    if cycle_index < 0:
        raise ValueError("cycle index cannot be negative")
    return _cycle_for(cycle_index, tuple(ordinary_profile_names), tuple(radio_ids), policy_id)


def _cycle_for(
    cycle_index: int,
    ordinary_profile_names: tuple[str, ...],
    radio_ids: tuple[str, ...],
    policy_id: str,
) -> tuple[ProductionDwellClass, ...]:
    if policy_id == MIXED_RATE_SCHEDULE_POLICY_V1:
        cycle_classes = _CYCLE_CLASSES
    elif policy_id == MIXED_RATE_10M_SCHEDULE_POLICY_V1:
        cycle_classes = _TEN_M_CYCLE_CLASSES
    elif policy_id == MIXED_RATE_SAFE_SCHEDULE_POLICY_V1:
        cycle_classes = _SAFE_CYCLE_CLASSES
    else:
        raise ValueError("mixed-rate schedule policy is unsupported")
    seed = canonical_digest(
        {
            "policy_id": policy_id,
            "cycle_index": cycle_index,
            "ordinary_profile_names": ordinary_profile_names,
            "radio_ids": radio_ids,
        }
    )
    decorated = [
        (
            hashlib.sha256(f"cycle-permutation-v1\0{seed}\0{index}".encode()).digest(),
            index,
            dwell_class,
        )
        for index, dwell_class in enumerate(cycle_classes)
    ]
    cycle = tuple(item[2] for item in sorted(decorated))
    assert Counter(cycle) == Counter(cycle_classes)
    return cycle


def _balanced_high_radio_index(
    *,
    cycle: tuple[ProductionDwellClass, ...],
    cycle_slot: int,
    dwell_class: ProductionDwellClass,
    cycle_index: int,
) -> int:
    same_class_rank = sum(1 for item in cycle[:cycle_slot] if item is dwell_class)
    return (same_class_rank + cycle_index) % 2


def _unbiased_index(modulus: int, *, domain: str, operation_key: str) -> int:
    sample_space = 1 << 256
    rejection_floor = sample_space - (sample_space % modulus)
    counter = 0
    while True:
        value = int.from_bytes(
            hashlib.sha256(
                f"mixed-rate-schedule-v1\0{domain}\0{operation_key}\0{counter}".encode()
            ).digest(),
            "big",
        )
        if value < rejection_floor:
            return value % modulus
        counter += 1
