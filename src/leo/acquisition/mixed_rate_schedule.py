"""Pure deterministic compiler for the production 16-dwell rate policy."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from leo.contracts.digests import canonical_digest
from leo.contracts.gain_control import GainControllerMode, GainControllerPolicyV1
from leo.contracts.mixed_rate_schedule import (
    MIXED_RATE_10M_SCHEDULE_POLICY_V1,
    MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
    MIXED_RATE_SCHEDULE_CYCLE_LENGTH,
    MIXED_RATE_SCHEDULE_POLICY_V1,
    PRODUCTION_NATIVE_RATE_CYCLE_LENGTH_V2,
    PRODUCTION_NATIVE_RATE_POLICY_V2,
    ProductionDwellClass,
    ProductionDwellClassV2,
    ProductionDwellIntentV1,
    ProductionDwellIntentV2,
    ProductionTuningBranchV2,
    ScheduledRadioLegV2,
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

_PRODUCTION_V2_CYCLE_CLASSES = (
    ProductionDwellClassV2.BOTH_2P5,
    ProductionDwellClassV2.BOTH_2P5,
    ProductionDwellClassV2.BOTH_5,
    ProductionDwellClassV2.BOTH_5,
    ProductionDwellClassV2.MIXED_2P5_5,
    ProductionDwellClassV2.MIXED_2P5_10,
    ProductionDwellClassV2.MIXED_2P5_15,
    ProductionDwellClassV2.MIXED_2P5_20,
)

ProductionProfileKey = tuple[int, tuple[int, ...], bool]
ProductionProfileAuthority = tuple[str, str, int]


def compile_production_dwell_intent_v2(
    *,
    operation_key: str,
    cadence_ordinal: int,
    radio_ids: Sequence[str],
    profile_authority: Mapping[ProductionProfileKey, ProductionProfileAuthority],
    extra_tags: Sequence[str] = (),
) -> ProductionDwellIntentV2:
    """Resolve one slot of the exact 8-dwell production policy."""

    if cadence_ordinal < 0:
        raise ValueError("cadence ordinal cannot be negative")
    radios = tuple(radio_ids)
    if len(radios) != 2 or len(set(radios)) != 2:
        raise ValueError("production V2 policy requires two unique radios")
    required_keys: set[ProductionProfileKey] = {
        (2_500_000, (0, 1), False),
        (5_000_000, (0, 1), False),
        (2_500_000, (0, 1), True),
        (5_000_000, (0, 1), True),
        *(
            (rate, (receiver,), True)
            for rate in (10_000_000, 15_000_000, 20_000_000)
            for receiver in (0, 1)
        ),
    }
    if not required_keys.issubset(profile_authority):
        missing = sorted(required_keys - set(profile_authority))
        raise ValueError(f"production profile authority omits required geometries: {missing}")
    cycle_index, cycle_slot = divmod(cadence_ordinal, PRODUCTION_NATIVE_RATE_CYCLE_LENGTH_V2)
    cycle = _production_v2_cycle(cycle_index, radios)
    dwell_class = cycle[cycle_slot]
    is_mixed = dwell_class.value.startswith("mixed_")
    high_rate = {
        ProductionDwellClassV2.BOTH_2P5: 2_500_000,
        ProductionDwellClassV2.BOTH_5: 5_000_000,
        ProductionDwellClassV2.MIXED_2P5_5: 5_000_000,
        ProductionDwellClassV2.MIXED_2P5_10: 10_000_000,
        ProductionDwellClassV2.MIXED_2P5_15: 15_000_000,
        ProductionDwellClassV2.MIXED_2P5_20: 20_000_000,
    }[dwell_class]
    if is_mixed:
        high_radio_id = tuple(sorted(radios))[
            _unbiased_index_v2(2, domain="high-radio", operation_key=operation_key)
        ]
        rates = {
            radio_id: (high_rate if radio_id == high_radio_id else 2_500_000) for radio_id in radios
        }
        tuning_branch = ProductionTuningBranchV2.SAME
        channel = 1 + _unbiased_index_v2(4, domain="channel", operation_key=operation_key)
        edge = _edge_v2(operation_key, domain="edge")
        tunings = dict.fromkeys(radios, (channel, edge))
    else:
        rates = dict.fromkeys(radios, high_rate)
        branch_draw = _unbiased_index_v2(4, domain="tuning-branch", operation_key=operation_key)
        if branch_draw == 0:
            tuning_branch = ProductionTuningBranchV2.SAME
            target = (
                1 + _unbiased_index_v2(4, domain="same-channel", operation_key=operation_key),
                _edge_v2(operation_key, domain="same-edge"),
            )
            tunings = dict.fromkeys(radios, target)
        elif branch_draw == 1:
            tuning_branch = ProductionTuningBranchV2.SAME_CHANNEL_OPPOSITE_EDGE
            channel = 1 + _unbiased_index_v2(
                4, domain="opposite-channel", operation_key=operation_key
            )
            first_edge = _edge_v2(operation_key, domain=f"opposite-edge:{sorted(radios)[0]}")
            tunings = {
                sorted(radios)[0]: (channel, first_edge),
                sorted(radios)[1]: (
                    channel,
                    StarlinkEdge.UPPER if first_edge is StarlinkEdge.LOWER else StarlinkEdge.LOWER,
                ),
            }
        else:
            tuning_branch = ProductionTuningBranchV2.INDEPENDENT
            tunings = {
                radio_id: (
                    1
                    + _unbiased_index_v2(
                        4, domain=f"independent-channel:{radio_id}", operation_key=operation_key
                    ),
                    _edge_v2(operation_key, domain=f"independent-edge:{radio_id}"),
                )
                for radio_id in radios
            }
    legs: list[ScheduledRadioLegV2] = []
    for radio_id in radios:
        rate = rates[radio_id]
        receiver_ids = (
            (
                _unbiased_index_v2(
                    2,
                    domain=f"high-receiver:{radio_id}",
                    operation_key=operation_key,
                ),
            )
            if is_mixed and rate > 5_000_000
            else (0, 1)
        )
        authority_key = (rate, receiver_ids, is_mixed)
        profile_name, revision_digest, refill_samples = profile_authority[authority_key]
        controller_mode = (
            GainControllerMode.TANDEM_HOLD
            if _unbiased_index_v2(
                2,
                domain=f"gain-controller:{radio_id}",
                operation_key=operation_key,
            )
            == 0
            else GainControllerMode.TANDEM_AUTO
        )
        channel, edge = tunings[radio_id]
        legs.append(
            ScheduledRadioLegV2(
                radio_id=radio_id,
                sample_rate_hz=cast(
                    Literal[2_500_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000],
                    rate,
                ),
                receiver_ids=cast(tuple[Literal[0, 1], ...], receiver_ids),
                profile_name=profile_name,
                profile_revision_digest=revision_digest,
                starlink_channel=channel,
                starlink_edge=edge,
                gain_controller=GainControllerPolicyV1.create(
                    controller_mode,
                    sample_count=refill_samples,
                ),
            )
        )
    values: dict[str, Any] = {
        "schema_version": 2,
        "policy_id": PRODUCTION_NATIVE_RATE_POLICY_V2,
        "operation_key": operation_key,
        "cadence_ordinal": cadence_ordinal,
        "cycle_index": cycle_index,
        "cycle_slot": cycle_slot,
        "dwell_class": dwell_class,
        "tuning_branch": tuning_branch,
        "radio_ids": radios,
        "radio_legs": tuple(legs),
        "extra_tags": tuple(sorted(set(extra_tags))),
    }
    candidate = ProductionDwellIntentV2.model_construct(
        intent_digest="sha256:" + "0" * 64,
        **values,
    )
    document = candidate.model_dump(mode="json", exclude={"intent_digest"})
    return ProductionDwellIntentV2.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
    )


def production_cycle_classes_v2(
    *, cycle_index: int, radio_ids: Sequence[str]
) -> tuple[ProductionDwellClassV2, ...]:
    if cycle_index < 0:
        raise ValueError("cycle index cannot be negative")
    radios = tuple(radio_ids)
    if len(radios) != 2 or len(set(radios)) != 2:
        raise ValueError("production V2 cycle requires two unique radios")
    return _production_v2_cycle(cycle_index, radios)


def _production_v2_cycle(
    cycle_index: int,
    radio_ids: tuple[str, ...],
) -> tuple[ProductionDwellClassV2, ...]:
    seed = canonical_digest(
        {
            "policy_id": PRODUCTION_NATIVE_RATE_POLICY_V2,
            "cycle_index": cycle_index,
            "radio_ids": sorted(radio_ids),
        }
    )
    decorated = [
        (
            hashlib.sha256(f"cycle-permutation-v2\0{seed}\0{index}".encode()).digest(),
            index,
            dwell_class,
        )
        for index, dwell_class in enumerate(_PRODUCTION_V2_CYCLE_CLASSES)
    ]
    cycle = tuple(item[2] for item in sorted(decorated))
    assert Counter(cycle) == Counter(_PRODUCTION_V2_CYCLE_CLASSES)
    return cycle


def _edge_v2(operation_key: str, *, domain: str) -> StarlinkEdge:
    return (
        StarlinkEdge.LOWER
        if _unbiased_index_v2(2, domain=domain, operation_key=operation_key) == 0
        else StarlinkEdge.UPPER
    )


def _unbiased_index_v2(modulus: int, *, domain: str, operation_key: str) -> int:
    sample_space = 1 << 256
    rejection_floor = sample_space - (sample_space % modulus)
    counter = 0
    while True:
        value = int.from_bytes(
            hashlib.sha256(
                f"production-native-rate-schedule-v2\0{domain}\0{operation_key}\0{counter}".encode()
            ).digest(),
            "big",
        )
        if value < rejection_floor:
            return value % modulus
        counter += 1


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
