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
    PRODUCTION_2P5_10_15_RATE_POLICY_V2,
    PRODUCTION_DIRECT_ASYNC_RATE_CYCLE_LENGTH_V3,
    PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3,
    PRODUCTION_NATIVE_RATE_CYCLE_LENGTH_V2,
    PRODUCTION_NATIVE_RATE_POLICY_V2,
    ProductionDwellClass,
    ProductionDwellClassV2,
    ProductionDwellClassV3,
    ProductionDwellIntentV1,
    ProductionDwellIntentV2,
    ProductionDwellIntentV3,
    ProductionTuningBranchV2,
    ScheduledRadioLegV2,
    ScheduledRadioLegV3,
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
_PRODUCTION_2P5_10_15_V2_CYCLE_CLASSES = (
    *(ProductionDwellClassV2.MIXED_2P5_10 for _ in range(4)),
    *(ProductionDwellClassV2.MIXED_2P5_15 for _ in range(4)),
)
_PRODUCTION_DIRECT_ASYNC_V3_CYCLE_CLASSES = (
    ProductionDwellClassV3.MIXED_2P5_10,
    ProductionDwellClassV3.MIXED_2P5_10,
    ProductionDwellClassV3.MIXED_2P5_15,
    ProductionDwellClassV3.MIXED_2P5_15,
    ProductionDwellClassV3.MIXED_2P5_25,
    ProductionDwellClassV3.MIXED_2P5_25,
)

# This is an operator-facing scheduler selector, not a new persisted intent
# contract. It compiles an ordinary immutable V3 rate/tuning intent whose
# explicit controller assignments are all HOLD and whose extra tag records the
# restricted rollout authority.
PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1 = "production-direct-async-2p5-10-15-25-hold-6-v1"
PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_TAG_V1 = "gain_rollout:tandem_hold_v1"
PRODUCTION_DIRECT_ASYNC_EXACT_LO_HOLD_ROLLOUT_POLICY_V2 = (
    "production-direct-async-2p5-10-15-25-hold-exact-lo-6-v2"
)
PRODUCTION_DIRECT_ASYNC_EXACT_LO_HOLD_ROLLOUT_TAG_V2 = "tuning_rollout:exact_lo_matrix_v2"
PRODUCTION_DIRECT_ASYNC_FIXED_25_HOLD_POLICY_V1 = "production-direct-async-2p5-25-hold-v1"
PRODUCTION_DIRECT_ASYNC_FIXED_25_HOLD_TAG_V1 = "rate_rollout:fixed_2p5_25_hold_v1"

ProductionProfileKey = tuple[int, tuple[int, ...], bool]
ProductionProfileAuthority = tuple[str, str, int]


def compile_production_dwell_intent_v3(
    *,
    operation_key: str,
    cadence_ordinal: int,
    radio_ids: Sequence[str],
    profile_authority: Mapping[ProductionProfileKey, ProductionProfileAuthority],
    policy_id: str = PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3,
    extra_tags: Sequence[str] = (),
    dwell_class_override: ProductionDwellClassV3 | None = None,
) -> ProductionDwellIntentV3:
    """Resolve one uniform same-target 2.5 x 10/15/25 MS/s dwell."""

    if cadence_ordinal < 0:
        raise ValueError("cadence ordinal cannot be negative")
    radios = tuple(radio_ids)
    if len(radios) != 2 or len(set(radios)) != 2:
        raise ValueError("production V3 policy requires two unique radios")
    if policy_id != PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3:
        raise ValueError("production V3 rate policy is unsupported")
    required_keys: set[ProductionProfileKey] = {
        (2_500_000, (0, 1), True),
        *(
            (rate, (receiver,), True)
            for rate in (10_000_000, 15_000_000, 25_000_000)
            for receiver in (0, 1)
        ),
    }
    if not required_keys.issubset(profile_authority):
        missing = sorted(required_keys - set(profile_authority))
        raise ValueError(f"production V3 profile authority omits geometries: {missing}")
    cycle_index, cycle_slot = divmod(cadence_ordinal, PRODUCTION_DIRECT_ASYNC_RATE_CYCLE_LENGTH_V3)
    cycle = production_cycle_classes_v3(cycle_index=cycle_index, radio_ids=radios)
    dwell_class = cycle[cycle_slot] if dwell_class_override is None else dwell_class_override
    high_rate = {
        ProductionDwellClassV3.MIXED_2P5_10: 10_000_000,
        ProductionDwellClassV3.MIXED_2P5_15: 15_000_000,
        ProductionDwellClassV3.MIXED_2P5_25: 25_000_000,
    }[dwell_class]
    high_radio_id = tuple(sorted(radios))[
        _unbiased_index_v3(2, domain="high-radio", operation_key=operation_key)
    ]
    channel = 1 + _unbiased_index_v3(4, domain="channel", operation_key=operation_key)
    edge = (
        StarlinkEdge.LOWER
        if _unbiased_index_v3(2, domain="edge", operation_key=operation_key) == 0
        else StarlinkEdge.UPPER
    )
    legs: list[ScheduledRadioLegV3] = []
    for radio_id in radios:
        rate = high_rate if radio_id == high_radio_id else 2_500_000
        receivers = (
            (
                _unbiased_index_v3(
                    2,
                    domain=f"high-receiver:{radio_id}",
                    operation_key=operation_key,
                ),
            )
            if rate != 2_500_000
            else (0, 1)
        )
        profile_name, revision_digest, refill_samples = profile_authority[(rate, receivers, True)]
        controller_mode = (
            GainControllerMode.TANDEM_HOLD
            if _unbiased_index_v3(
                2,
                domain=f"gain-controller:{radio_id}",
                operation_key=operation_key,
            )
            == 0
            else GainControllerMode.TANDEM_AUTO
        )
        legs.append(
            ScheduledRadioLegV3(
                radio_id=radio_id,
                sample_rate_hz=cast(Literal[2_500_000, 10_000_000, 15_000_000, 25_000_000], rate),
                receiver_ids=cast(tuple[Literal[0, 1], ...], receivers),
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
        "schema_version": 3,
        "policy_id": policy_id,
        "operation_key": operation_key,
        "cadence_ordinal": cadence_ordinal,
        "cycle_index": cycle_index,
        "cycle_slot": cycle_slot,
        "dwell_class": dwell_class,
        "tuning_branch": ProductionTuningBranchV2.SAME,
        "radio_ids": radios,
        "radio_legs": tuple(legs),
        "extra_tags": tuple(sorted(set(extra_tags))),
    }
    candidate = ProductionDwellIntentV3.model_construct(
        intent_digest="sha256:" + "0" * 64,
        **values,
    )
    document = candidate.model_dump(mode="json", exclude={"intent_digest"})
    return ProductionDwellIntentV3.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
    )


def compile_production_dwell_intent_hold_rollout_v1(
    *,
    operation_key: str,
    cadence_ordinal: int,
    radio_ids: Sequence[str],
    profile_authority: Mapping[ProductionProfileKey, ProductionProfileAuthority],
    rollout_policy_id: str = PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1,
    extra_tags: Sequence[str] = (),
) -> ProductionDwellIntentV3:
    """Compile the additive HOLD-only rollout into an immutable V3 intent."""

    if rollout_policy_id != PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_POLICY_V1:
        raise ValueError("direct-async HOLD rollout policy is unsupported")
    intent = compile_production_dwell_intent_v3(
        operation_key=operation_key,
        cadence_ordinal=cadence_ordinal,
        radio_ids=radio_ids,
        profile_authority=profile_authority,
        extra_tags=(*extra_tags, PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_TAG_V1),
    )
    return _with_tandem_hold_v1(intent, profile_authority=profile_authority)


def compile_production_dwell_intent_exact_lo_hold_rollout_v2(
    *,
    operation_key: str,
    cadence_ordinal: int,
    radio_ids: Sequence[str],
    profile_authority: Mapping[ProductionProfileKey, ProductionProfileAuthority],
    rollout_policy_id: str = PRODUCTION_DIRECT_ASYNC_EXACT_LO_HOLD_ROLLOUT_POLICY_V2,
    extra_tags: Sequence[str] = (),
) -> ProductionDwellIntentV3:
    """Compile HOLD-only V3 intents over the qualified exact-LO target matrix.

    AD9361 integer readback skips make the channel 1--3 ideal 15 MHz
    lower-edge and 25 MHz upper-edge centers impossible to apply exactly on the
    production radios.  Both edges close exactly on channel 4, while the
    complementary edges close on every channel.  The immutable V3 intent and
    V5 capture-plan contracts remain unchanged; this selector only redirects
    an impossible target to its same-channel qualified edge.
    """

    if rollout_policy_id != PRODUCTION_DIRECT_ASYNC_EXACT_LO_HOLD_ROLLOUT_POLICY_V2:
        raise ValueError("exact-LO HOLD rollout policy is unsupported")
    intent = compile_production_dwell_intent_v3(
        operation_key=operation_key,
        cadence_ordinal=cadence_ordinal,
        radio_ids=radio_ids,
        profile_authority=profile_authority,
        extra_tags=(
            *extra_tags,
            PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_TAG_V1,
            PRODUCTION_DIRECT_ASYNC_EXACT_LO_HOLD_ROLLOUT_TAG_V2,
        ),
    )
    intent = _with_exact_lo_qualified_edge_v2(intent)
    return _with_tandem_hold_v1(intent, profile_authority=profile_authority)


def compile_production_fixed_25_hold_intent_v1(
    *,
    operation_key: str,
    cadence_ordinal: int,
    radio_ids: Sequence[str],
    profile_authority: Mapping[ProductionProfileKey, ProductionProfileAuthority],
    rollout_policy_id: str = PRODUCTION_DIRECT_ASYNC_FIXED_25_HOLD_POLICY_V1,
    extra_tags: Sequence[str] = (),
) -> ProductionDwellIntentV3:
    """Compile one fixed 2.5 x 25 MS/s operator dwell on the V3 path."""

    if rollout_policy_id != PRODUCTION_DIRECT_ASYNC_FIXED_25_HOLD_POLICY_V1:
        raise ValueError("fixed 2.5 x 25 MS/s HOLD policy is unsupported")
    intent = compile_production_dwell_intent_v3(
        operation_key=operation_key,
        cadence_ordinal=cadence_ordinal,
        radio_ids=radio_ids,
        profile_authority=profile_authority,
        dwell_class_override=ProductionDwellClassV3.MIXED_2P5_25,
        extra_tags=(
            *extra_tags,
            PRODUCTION_DIRECT_ASYNC_HOLD_ROLLOUT_TAG_V1,
            PRODUCTION_DIRECT_ASYNC_FIXED_25_HOLD_TAG_V1,
        ),
    )
    return _with_tandem_hold_v1(intent, profile_authority=profile_authority)


def _with_tandem_hold_v1(
    intent: ProductionDwellIntentV3,
    *,
    profile_authority: Mapping[ProductionProfileKey, ProductionProfileAuthority],
) -> ProductionDwellIntentV3:
    legs = tuple(
        leg.model_copy(
            update={
                "gain_controller": GainControllerPolicyV1.create(
                    GainControllerMode.TANDEM_HOLD,
                    sample_count=profile_authority[(leg.sample_rate_hz, leg.receiver_ids, True)][2],
                )
            }
        )
        for leg in intent.radio_legs
    )
    document = intent.model_dump(mode="json", exclude={"intent_digest"})
    document["radio_legs"] = [leg.model_dump(mode="json") for leg in legs]
    return ProductionDwellIntentV3.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
    )


def _with_exact_lo_qualified_edge_v2(
    intent: ProductionDwellIntentV3,
) -> ProductionDwellIntentV3:
    channel = intent.radio_legs[0].starlink_channel
    selected_edge = (
        StarlinkEdge.UPPER
        if intent.dwell_class is ProductionDwellClassV3.MIXED_2P5_15 and channel < 4
        else (
            StarlinkEdge.LOWER
            if intent.dwell_class is ProductionDwellClassV3.MIXED_2P5_25 and channel < 4
            else None
        )
    )
    if selected_edge is None:
        return intent
    legs = tuple(
        leg.model_copy(update={"starlink_edge": selected_edge}) for leg in intent.radio_legs
    )
    document = intent.model_dump(mode="json", exclude={"intent_digest"})
    document["radio_legs"] = [leg.model_dump(mode="json") for leg in legs]
    return ProductionDwellIntentV3.model_validate(
        {**document, "intent_digest": canonical_digest(document)}
    )


def production_cycle_classes_v3(
    *, cycle_index: int, radio_ids: Sequence[str]
) -> tuple[ProductionDwellClassV3, ...]:
    if cycle_index < 0:
        raise ValueError("cycle index cannot be negative")
    radios = tuple(radio_ids)
    if len(radios) != 2 or len(set(radios)) != 2:
        raise ValueError("production V3 cycle requires two unique radios")
    seed = canonical_digest(
        {
            "policy_id": PRODUCTION_DIRECT_ASYNC_RATE_POLICY_V3,
            "cycle_index": cycle_index,
            "radio_ids": sorted(radios),
        }
    )
    decorated = [
        (
            hashlib.sha256(f"cycle-permutation-v3\0{seed}\0{index}".encode()).digest(),
            index,
            dwell_class,
        )
        for index, dwell_class in enumerate(_PRODUCTION_DIRECT_ASYNC_V3_CYCLE_CLASSES)
    ]
    cycle = tuple(item[2] for item in sorted(decorated))
    assert Counter(cycle) == Counter(_PRODUCTION_DIRECT_ASYNC_V3_CYCLE_CLASSES)
    return cycle


def _unbiased_index_v3(modulus: int, *, domain: str, operation_key: str) -> int:
    sample_space = 1 << 256
    rejection_floor = sample_space - sample_space % modulus
    counter = 0
    while True:
        value = int.from_bytes(
            hashlib.sha256(
                f"production-direct-async-rate-schedule-v3\0{domain}\0"
                f"{operation_key}\0{counter}".encode()
            ).digest(),
            "big",
        )
        if value < rejection_floor:
            return value % modulus
        counter += 1


def compile_production_dwell_intent_v2(
    *,
    operation_key: str,
    cadence_ordinal: int,
    radio_ids: Sequence[str],
    profile_authority: Mapping[ProductionProfileKey, ProductionProfileAuthority],
    policy_id: str = PRODUCTION_NATIVE_RATE_POLICY_V2,
    extra_tags: Sequence[str] = (),
) -> ProductionDwellIntentV2:
    """Resolve one slot of an exact 8-dwell production policy."""

    if cadence_ordinal < 0:
        raise ValueError("cadence ordinal cannot be negative")
    radios = tuple(radio_ids)
    if len(radios) != 2 or len(set(radios)) != 2:
        raise ValueError("production V2 policy requires two unique radios")
    if policy_id not in {
        PRODUCTION_NATIVE_RATE_POLICY_V2,
        PRODUCTION_2P5_10_15_RATE_POLICY_V2,
    }:
        raise ValueError("production V2 rate policy is unsupported")
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
    cycle = _production_v2_cycle(cycle_index, radios, policy_id)
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
        "policy_id": policy_id,
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
    *,
    cycle_index: int,
    radio_ids: Sequence[str],
    policy_id: str = PRODUCTION_NATIVE_RATE_POLICY_V2,
) -> tuple[ProductionDwellClassV2, ...]:
    if cycle_index < 0:
        raise ValueError("cycle index cannot be negative")
    radios = tuple(radio_ids)
    if len(radios) != 2 or len(set(radios)) != 2:
        raise ValueError("production V2 cycle requires two unique radios")
    if policy_id not in {
        PRODUCTION_NATIVE_RATE_POLICY_V2,
        PRODUCTION_2P5_10_15_RATE_POLICY_V2,
    }:
        raise ValueError("production V2 rate policy is unsupported")
    return _production_v2_cycle(cycle_index, radios, policy_id)


def _production_v2_cycle(
    cycle_index: int,
    radio_ids: tuple[str, ...],
    policy_id: str,
) -> tuple[ProductionDwellClassV2, ...]:
    cycle_classes = (
        _PRODUCTION_2P5_10_15_V2_CYCLE_CLASSES
        if policy_id == PRODUCTION_2P5_10_15_RATE_POLICY_V2
        else _PRODUCTION_V2_CYCLE_CLASSES
    )
    seed = canonical_digest(
        {
            "policy_id": policy_id,
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
        for index, dwell_class in enumerate(cycle_classes)
    ]
    cycle = tuple(item[2] for item in sorted(decorated))
    assert Counter(cycle) == Counter(cycle_classes)
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
