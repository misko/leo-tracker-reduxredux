from __future__ import annotations

from collections import Counter, deque
from decimal import Decimal
from random import Random

from leo.acquisition.starlink_tuning import (
    PairedTuningBranch,
    sample_paired_starlink_tuning,
)
from leo.contracts.profile import CaptureProfileV1
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.states import GainMode, StarlinkEdge


class Draws:
    def __init__(self, *values: int) -> None:
        self.values = deque(values)

    def __call__(self, limit: int) -> int:
        value = self.values.popleft()
        assert 0 <= value < limit
        return value


def _profile() -> CaptureProfileV1:
    return CaptureProfileV1(
        name="random-tuning-test",
        center_frequency_hz=1_709_687_500,
        rf_center_frequency_hz=11_459_687_500,
        lnb_lo_hz=9_750_000_000,
        starlink_channel="ch4",
        starlink_edge=StarlinkEdge.LOWER,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30),
            ReceiverGainV1(receiver_id=1, gain_db=30),
        ),
        duration_seconds=Decimal(60),
    )


def test_same_branch_uses_one_uniform_channel_and_edge_for_both_radios() -> None:
    selection = sample_paired_starlink_tuning(("radio-a", "radio-b"), randbelow=Draws(0, 2, 1))

    assert selection.branch is PairedTuningBranch.SAME
    assert selection.radio_tunings[0][1] == selection.radio_tunings[1][1]
    assert selection.radio_tunings[0][1].channel == 3
    assert selection.radio_tunings[0][1].edge is StarlinkEdge.UPPER
    assert selection.radio_tunings[0][1].center_frequency_hz == 1_690_312_500


def test_opposite_branch_uses_one_channel_and_opposite_uniform_first_edge() -> None:
    selection = sample_paired_starlink_tuning(("radio-a", "radio-b"), randbelow=Draws(1, 0, 0))

    first = selection.radio_tunings[0][1]
    second = selection.radio_tunings[1][1]
    assert selection.branch is PairedTuningBranch.SAME_CHANNEL_OPPOSITE_EDGE
    assert first.channel == second.channel == 1
    assert (first.edge, second.edge) == (StarlinkEdge.LOWER, StarlinkEdge.UPPER)
    assert (first.center_frequency_hz, second.center_frequency_hz) == (
        959_687_500,
        1_190_312_500,
    )


def test_independent_branch_draws_both_complete_tunings_independently() -> None:
    selection = sample_paired_starlink_tuning(
        ("radio-a", "radio-b"), randbelow=Draws(3, 3, 0, 1, 1)
    )

    assert selection.branch is PairedTuningBranch.INDEPENDENT
    assert selection.manifest_tags == (
        "tuning:stream-0:ch4:lower",
        "tuning:stream-1:ch2:upper",
        "tuning_policy:independent",
    )
    settings = selection.requested_settings(_profile())
    assert settings["radio-a"].center_frequency_hz == 1_709_687_500
    assert settings["radio-b"].center_frequency_hz == 1_440_312_500
    assert settings["radio-a"].receiver_ids == settings["radio-b"].receiver_ids == (0, 1)


def test_seeded_distribution_is_uniform_with_requested_mixture() -> None:
    random = Random(20260820)
    branch_counts: Counter[PairedTuningBranch] = Counter()
    independent_states: Counter[tuple[int, StarlinkEdge]] = Counter()
    for _ in range(80_000):
        selection = sample_paired_starlink_tuning(
            ("radio-a", "radio-b"), randbelow=random.randrange
        )
        branch_counts[selection.branch] += 1
        if selection.branch is PairedTuningBranch.INDEPENDENT:
            independent_states.update(
                (tuning.channel, tuning.edge) for _, tuning in selection.radio_tunings
            )

    assert abs(branch_counts[PairedTuningBranch.SAME] / 80_000 - 0.25) < 0.01
    assert abs(branch_counts[PairedTuningBranch.SAME_CHANNEL_OPPOSITE_EDGE] / 80_000 - 0.25) < 0.01
    assert abs(branch_counts[PairedTuningBranch.INDEPENDENT] / 80_000 - 0.50) < 0.01
    expected = sum(independent_states.values()) / 8
    assert len(independent_states) == 8
    assert all(abs(count - expected) / expected < 0.04 for count in independent_states.values())
