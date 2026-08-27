from __future__ import annotations

from collections import Counter

import pytest

from leo.acquisition.mixed_rate_schedule import (
    compile_production_dwell_intent_v1,
    production_cycle_classes_v1,
)
from leo.contracts.mixed_rate_schedule import (
    MIXED_RATE_10M_SCHEDULE_POLICY_V1,
    MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
    ProductionDwellClass,
    ProductionDwellIntentV1,
)

_PROFILES = ("ordinary-2p5", "ordinary-3", "ordinary-5")
_RADIOS = ("radio-20", "radio-21")
_RATE_PROFILES = {
    2_500_000: ("rate-2p5", "sha256:" + "2" * 64),
    5_000_000: ("rate-5", "sha256:" + "5" * 64),
    10_000_000: ("rate-10", "sha256:" + "a" * 64),
    15_000_000: ("rate-15", "sha256:" + "f" * 64),
}


def _intent(ordinal: int) -> ProductionDwellIntentV1:
    return compile_production_dwell_intent_v1(
        operation_key=f"scheduled-dwell:pool:2026-08-27T00:{ordinal:02d}:00+00:00",
        cadence_ordinal=ordinal,
        ordinary_profile_names=_PROFILES,
        radio_ids=_RADIOS,
        rate_profile_authority=_RATE_PROFILES,
        extra_tags=("mixed-rate", "scheduled"),
    )


def test_each_cycle_has_exact_requested_class_allocation() -> None:
    for cycle_index in range(100):
        cycle = production_cycle_classes_v1(
            cycle_index=cycle_index,
            ordinary_profile_names=_PROFILES,
            radio_ids=_RADIOS,
        )
        assert Counter(cycle) == {
            ProductionDwellClass.MIXED_2P5_5: 6,
            ProductionDwellClass.MIXED_2P5_15: 2,
            ProductionDwellClass.ORDINARY_POOL: 8,
        }


def test_safe_policy_preserves_five_m_share_and_cannot_schedule_fifteen_m() -> None:
    cycle = production_cycle_classes_v1(
        cycle_index=0,
        ordinary_profile_names=_PROFILES,
        radio_ids=_RADIOS,
        policy_id=MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
    )
    assert Counter(cycle) == {
        ProductionDwellClass.MIXED_2P5_5: 6,
        ProductionDwellClass.ORDINARY_POOL: 10,
    }
    intents = tuple(
        compile_production_dwell_intent_v1(
            operation_key=f"safe-dwell:{ordinal}",
            cadence_ordinal=ordinal,
            ordinary_profile_names=_PROFILES,
            radio_ids=_RADIOS,
            rate_profile_authority={
                key: value for key, value in _RATE_PROFILES.items() if key != 15_000_000
            },
            policy_id=MIXED_RATE_SAFE_SCHEDULE_POLICY_V1,
        )
        for ordinal in range(16)
    )
    assert all(item.dwell_class is not ProductionDwellClass.MIXED_2P5_15 for item in intents)
    assert all(rate.sample_rate_hz != 15_000_000 for item in intents for rate in item.radio_rates)


def test_ten_m_policy_has_exact_requested_allocation_and_balanced_roles() -> None:
    intents = tuple(
        compile_production_dwell_intent_v1(
            operation_key=f"ten-dwell:{ordinal}",
            cadence_ordinal=ordinal,
            ordinary_profile_names=_PROFILES,
            radio_ids=_RADIOS,
            rate_profile_authority={
                key: value for key, value in _RATE_PROFILES.items() if key != 15_000_000
            },
            policy_id=MIXED_RATE_10M_SCHEDULE_POLICY_V1,
        )
        for ordinal in range(16)
    )

    assert Counter(item.dwell_class for item in intents) == {
        ProductionDwellClass.MIXED_2P5_5: 6,
        ProductionDwellClass.MIXED_2P5_10: 2,
        ProductionDwellClass.ORDINARY_POOL: 8,
    }
    ten = Counter(
        next(rate.radio_id for rate in item.radio_rates if rate.sample_rate_hz == 10_000_000)
        for item in intents
        if item.dwell_class is ProductionDwellClass.MIXED_2P5_10
    )
    assert ten == {_RADIOS[0]: 1, _RADIOS[1]: 1}


def test_rate_roles_are_balanced_within_every_cycle() -> None:
    for cycle_index in range(32):
        intents = tuple(_intent(cycle_index * 16 + slot) for slot in range(16))
        five = Counter(
            next(item.radio_id for item in intent.radio_rates if item.sample_rate_hz == 5_000_000)
            for intent in intents
            if intent.dwell_class is ProductionDwellClass.MIXED_2P5_5
        )
        fifteen = Counter(
            next(item.radio_id for item in intent.radio_rates if item.sample_rate_hz == 15_000_000)
            for intent in intents
            if intent.dwell_class is ProductionDwellClass.MIXED_2P5_15
        )
        assert five == {_RADIOS[0]: 3, _RADIOS[1]: 3}
        assert fifteen == {_RADIOS[0]: 1, _RADIOS[1]: 1}


def test_mixed_intent_has_one_common_channel_edge_and_exact_rate_pair() -> None:
    mixed = next(
        intent
        for intent in (_intent(slot) for slot in range(16))
        if intent.dwell_class is ProductionDwellClass.MIXED_2P5_15
    )
    assert 1 <= mixed.starlink_channel <= 4
    assert mixed.starlink_edge is not None
    assert {item.sample_rate_hz for item in mixed.radio_rates} == {2_500_000, 15_000_000}
    assert ProductionDwellIntentV1.model_validate_json(mixed.model_dump_json()) == mixed


def test_same_durable_key_and_slot_reproduce_byte_identical_intent() -> None:
    first = _intent(7)
    second = _intent(7)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.intent_digest == second.intent_digest


def test_tuning_and_ordinary_profile_domains_reach_all_states() -> None:
    intents = tuple(_intent(index) for index in range(16 * 64))
    mixed = tuple(
        intent for intent in intents if intent.dwell_class is not ProductionDwellClass.ORDINARY_POOL
    )
    assert {intent.starlink_channel for intent in mixed} == {1, 2, 3, 4}
    assert {intent.starlink_edge.value for intent in mixed if intent.starlink_edge is not None} == {
        "lower",
        "upper",
    }
    assert {
        intent.ordinary_profile_name
        for intent in intents
        if intent.dwell_class is ProductionDwellClass.ORDINARY_POOL
    } == set(_PROFILES)


def test_contract_rejects_rate_pair_or_digest_tamper() -> None:
    source = next(
        intent
        for intent in (_intent(slot) for slot in range(16))
        if intent.dwell_class is ProductionDwellClass.MIXED_2P5_5
    )
    wrong_rate = source.model_dump(mode="json")
    wrong_rate["radio_rates"][1]["sample_rate_hz"] = 15_000_000
    with pytest.raises(ValueError, match="rate pair"):
        ProductionDwellIntentV1.model_validate(wrong_rate)

    wrong_digest = source.model_copy(update={"intent_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="digest"):
        ProductionDwellIntentV1.model_validate(wrong_digest.model_dump(mode="json"))
