from __future__ import annotations

from collections import Counter

import pytest

from leo.acquisition.mixed_rate_schedule import (
    compile_production_dwell_intent_v2,
    production_cycle_classes_v2,
)
from leo.contracts.gain_control import GainControllerMode
from leo.contracts.mixed_rate_schedule import (
    ProductionDwellClassV2,
    ProductionDwellIntentV2,
    ProductionTuningBranchV2,
)

_RADIOS = ("radio-20", "radio-21")
_DIGESTS = {
    key: f"sha256:{index:064x}"
    for index, key in enumerate(
        (
            (2_500_000, (0, 1), False),
            (5_000_000, (0, 1), False),
            (2_500_000, (0, 1), True),
            (5_000_000, (0, 1), True),
            (10_000_000, (0,), True),
            (10_000_000, (1,), True),
            (15_000_000, (0,), True),
            (15_000_000, (1,), True),
            (20_000_000, (0,), True),
            (20_000_000, (1,), True),
        ),
        start=1,
    )
}
_AUTHORITY = {
    key: (f"profile-{rate}-{''.join(map(str, receivers))}-{int(mixed)}", digest, 1_048_576)
    for key, digest in _DIGESTS.items()
    for rate, receivers, mixed in (key,)
}


def _intent(ordinal: int, *, radios: tuple[str, str] = _RADIOS) -> ProductionDwellIntentV2:
    return compile_production_dwell_intent_v2(
        operation_key=f"scheduled-production-dwell:{ordinal}",
        cadence_ordinal=ordinal,
        radio_ids=radios,
        profile_authority=_AUTHORITY,
        extra_tags=("production-rate-policy", "scheduled"),
    )


def test_every_cycle_has_the_exact_eight_slot_probability_bag() -> None:
    expected = {
        ProductionDwellClassV2.BOTH_2P5: 2,
        ProductionDwellClassV2.BOTH_5: 2,
        ProductionDwellClassV2.MIXED_2P5_5: 1,
        ProductionDwellClassV2.MIXED_2P5_10: 1,
        ProductionDwellClassV2.MIXED_2P5_15: 1,
        ProductionDwellClassV2.MIXED_2P5_20: 1,
    }
    for cycle_index in range(128):
        assert (
            Counter(production_cycle_classes_v2(cycle_index=cycle_index, radio_ids=_RADIOS))
            == expected
        )


def test_policy_randomizes_physical_high_radio_single_rx_and_tandem_mode() -> None:
    intents = tuple(_intent(ordinal) for ordinal in range(8 * 512))
    mixed = tuple(item for item in intents if item.dwell_class.value.startswith("mixed_"))
    high_legs = tuple(
        next(leg for leg in item.radio_legs if leg.sample_rate_hz > 2_500_000) for item in mixed
    )
    single_high = tuple(leg for leg in high_legs if leg.sample_rate_hz > 5_000_000)

    assert {leg.radio_id for leg in high_legs} == set(_RADIOS)
    assert {leg.receiver_ids for leg in single_high} == {(0,), (1,)}
    assert {leg.gain_controller.mode for item in intents for leg in item.radio_legs} == {
        GainControllerMode.TANDEM_HOLD,
        GainControllerMode.TANDEM_AUTO,
    }


def test_same_rate_tuning_is_25_25_50_and_mixed_is_common_target() -> None:
    intents = tuple(_intent(ordinal) for ordinal in range(8 * 1024))
    same_rate = tuple(item for item in intents if not item.dwell_class.value.startswith("mixed_"))
    observed = Counter(item.tuning_branch for item in same_rate)
    total = len(same_rate)
    assert abs(observed[ProductionTuningBranchV2.SAME] / total - 0.25) < 0.03
    assert abs(observed[ProductionTuningBranchV2.SAME_CHANNEL_OPPOSITE_EDGE] / total - 0.25) < 0.03
    assert abs(observed[ProductionTuningBranchV2.INDEPENDENT] / total - 0.50) < 0.03
    for item in intents:
        if item.dwell_class.value.startswith("mixed_"):
            assert item.tuning_branch is ProductionTuningBranchV2.SAME
            assert len({(leg.starlink_channel, leg.starlink_edge) for leg in item.radio_legs}) == 1


def test_radio_configuration_order_does_not_bias_cycle_or_random_roles() -> None:
    for ordinal in range(8 * 32):
        forward = _intent(ordinal)
        reverse = _intent(ordinal, radios=tuple(reversed(_RADIOS)))
        assert forward.dwell_class is reverse.dwell_class
        forward_by_radio = {item.radio_id: item for item in forward.radio_legs}
        reverse_by_radio = {item.radio_id: item for item in reverse.radio_legs}
        assert forward_by_radio == reverse_by_radio


def test_intent_round_trips_and_rejects_receiver_or_digest_tamper() -> None:
    source = next(
        item
        for item in (_intent(ordinal) for ordinal in range(8))
        if item.dwell_class is ProductionDwellClassV2.MIXED_2P5_20
    )
    assert ProductionDwellIntentV2.model_validate_json(source.model_dump_json()) == source

    wrong_receiver = source.model_dump(mode="json")
    high = next(
        item for item in wrong_receiver["radio_legs"] if item["sample_rate_hz"] == 20_000_000
    )
    high["receiver_ids"] = [0, 1]
    with pytest.raises(ValueError, match="receiver geometry"):
        ProductionDwellIntentV2.model_validate(wrong_receiver)

    wrong_digest = source.model_copy(update={"intent_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="digest"):
        ProductionDwellIntentV2.model_validate(wrong_digest.model_dump(mode="json"))
