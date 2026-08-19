from __future__ import annotations

import numpy as np
import pytest

from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.states import ContinuityStatus, GainMode
from leo.radio.fake import FakeRadioError, FakeRadioSource


def _settings(receivers: tuple[int, ...]) -> RadioSettingsV1:
    return RadioSettingsV1(
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=2_500_000,
        bandwidth_hz=2_500_000,
        receiver_ids=receivers,
        gain_mode=GainMode.MANUAL,
        gains=tuple(ReceiverGainV1(receiver_id=receiver, gain_db=30.0) for receiver in receivers),
    )


@pytest.mark.parametrize("receivers", [(0,), (1,), (0, 1)])
def test_fake_radio_emits_deterministic_one_or_two_receiver_ci16(
    receivers: tuple[int, ...],
) -> None:
    first_radio = FakeRadioSource("fake-a", receiver_count=2, seed=5)
    second_radio = FakeRadioSource("fake-a", receiver_count=2, seed=5)
    for radio in (first_radio, second_radio):
        radio.open()
        assert radio.configure(_settings(receivers)) == _settings(receivers)

    first = first_radio.read_block(4)
    duplicate = second_radio.read_block(4)

    np.testing.assert_array_equal(first.samples, duplicate.samples)
    assert first.samples.shape == (4, len(receivers), 2)
    expected_receiver = receivers[0]
    assert first.samples[0, 0].tolist() == [
        -32_763 + expected_receiver * 1_009,
        -32_733 + expected_receiver * 2_003,
    ]
    assert first.metadata.session_sample_start == 0
    assert first.metadata.device_sample_counter == 0
    assert first.metadata.continuity is ContinuityStatus.UNKNOWN

    second = first_radio.read_block(3)
    assert second.metadata.session_sample_start == 4
    assert second.metadata.device_sample_counter == 4
    assert second.metadata.source_sequence == 1
    assert second.metadata.continuity is ContinuityStatus.CONTIGUOUS


def test_fake_radio_records_injected_gaps_without_hiding_them() -> None:
    radio = FakeRadioSource("fake-a", gaps_before_blocks={1: 3})
    radio.open()
    radio.configure(_settings((0, 1)))
    radio.read_block(4)
    block = radio.read_block(4)

    assert block.metadata.session_sample_start == 4
    assert block.metadata.device_sample_counter == 7
    assert block.metadata.continuity is ContinuityStatus.GAP_BEFORE
    assert block.metadata.missing_samples_before == 3


def test_fake_radio_enforces_lifecycle_capabilities_and_failures() -> None:
    radio = FakeRadioSource("fake-a", receiver_count=1, fail_after_blocks=1)
    with pytest.raises(FakeRadioError, match="not open"):
        radio.read_block(1)
    radio.open()
    with pytest.raises(FakeRadioError, match="unsupported receiver"):
        radio.configure(_settings((0, 1)))
    radio.configure(_settings((0,)))
    radio.read_block(1)
    with pytest.raises(FakeRadioError, match="injected failure"):
        radio.read_block(1)
    radio.close()
    with pytest.raises(FakeRadioError, match="not open"):
        radio.configure(_settings((0,)))
