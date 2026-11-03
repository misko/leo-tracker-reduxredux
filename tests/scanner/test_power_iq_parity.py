from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from leo.scanner.power_iq_parity import (
    ParityFrame,
    PowerIqCounterMappingV1,
    ci16_from_complex,
    qualify_power_iq,
    same_sample_window,
)


def mapping():
    return PowerIqCounterMappingV1(
        fpga_artifact_sha256="sha256:" + "1" * 64,
        packer_source_sha256="sha256:" + "2" * 64,
        evidence_sha256="sha256:" + "3" * 64,
        declared_by="synthetic component fixture",
    )


def fixture():
    random = np.random.default_rng(9343)
    samples = random.integers(-2046, 2047, (100000, 2, 2), dtype=np.int16)
    origin = (1 << 32) - 25000
    start = origin + 12345
    samples[12345, :, :] = [[-32768, 32767], [-2048, 2047]]
    frames = [
        ParityFrame(samples[:50000], origin + 1, 7, 0),
        ParityFrame(samples[50000:], origin + 50001, 7, 1),
    ]
    window = samples[12345:62345]
    words = [0] * 36
    words[:6] = [0x50575231, 0x00010000, 64, 50000, 1, 2]
    for index, value in ((10, start), (12, start + 50000)):
        words[index : index + 2] = [value & 0xFFFFFFFF, value >> 32]
    # Independent Python arbitrary-precision integer oracle, including rails.
    for rx in range(2):
        tuples = [(int(i), int(q)) for i, q in window[:, rx, :]]
        values = (
            (14 + rx * 2, sum(i * i + q * q for i, q in tuples)),
            (18 + rx * 4, sum(i for i, q in tuples)),
            (20 + rx * 4, sum(q for i, q in tuples)),
        )
        for index, value in values:
            value &= (1 << 64) - 1
            words[index : index + 2] = [value & 0xFFFFFFFF, value >> 32]
        words[26 + rx * 2] = sum(i in (-32768, 32767) for i, q in tuples)
        words[27 + rx * 2] = sum(q in (-32768, 32767) for i, q in tuples)
        words[30 + rx] = sum(i in (-2048, 2047) or q in (-2048, 2047) for i, q in tuples)
        words[32 + rx] = max(max(abs(i), abs(q)) for i, q in tuples)
    return frames, words, window


def test_exact_cross_frame_counter_wrap_and_python_integer_parity():
    frames, words, window = fixture()
    result = qualify_power_iq(
        frames, words, mapping=mapping(), session=1, generation=2, adc12_qualified=True
    )
    assert result["passed"] and result["sample_end_exclusive"] > 1 << 32
    assert result["expected"] == result["observed"] and result["qualified_tracking"] is False
    assert result["expected"][0]["peak_abs_component"] == 32768
    assert not result["observed_signed12_range"]
    np.testing.assert_array_equal(
        same_sample_window(
            frames, result["sample_start"], result["sample_end_exclusive"], mapping()
        ),
        window,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"fifo_start": (1 << 32) + 25002},
        {"generation": 8},
        {"buffer_sequence": 2},
        {"missing_samples_before": 1},
        {"overflow": True},
    ],
)
def test_gap_generation_counter_and_overflow_never_pad(change):
    frames, words, _ = fixture()
    frames[1] = replace(frames[1], **change)
    with pytest.raises(ValueError):
        qualify_power_iq(
            frames, words, mapping=mapping(), session=1, generation=2, adc12_qualified=True
        )


def test_corrupt_energy_mismatch_and_partial_identity_rejection():
    frames, words, _ = fixture()
    words[14] ^= 1
    result = qualify_power_iq(
        frames, words, mapping=mapping(), session=1, generation=2, adc12_qualified=True
    )
    assert not result["passed"] and result["mismatches"][0]["field"] == "energy_sum"
    for index in (0, 1, 3, 4, 5, 6, 7, 8, 9, 34, 35):
        broken = list(words)
        broken[index] ^= 1
        with pytest.raises(ValueError):
            qualify_power_iq(
                frames, broken, mapping=mapping(), session=1, generation=2, adc12_qualified=True
            )


def test_stationary_iq_aggregate_parity_cannot_qualify_counter_offset():
    samples = np.zeros((100000, 2, 2), dtype="<i2")
    # Both supports cover the requested interval. The second has wrong FIFO tags.
    correct = [ParityFrame(samples[:50000], 1, 7, 0), ParityFrame(samples[50000:], 50001, 7, 1)]
    shifted = [replace(frame, fifo_start=frame.fifo_start + 1) for frame in correct]
    words = [0] * 36
    words[:6] = [0x50575231, 0x00010000, 0, 50000, 1, 2]
    words[10], words[12] = 12345, 62345
    for frames in (correct, shifted):
        result = qualify_power_iq(
            frames, words, mapping=mapping(), session=1, generation=2, adc12_qualified=False
        )
        assert result["numerical_parity_passed"]
        assert result["mapping_independently_validated"] is False
        assert result["physical_mapping_qualified"] is False


def test_complex_integer_conversion_requires_exact_unscaled_ci16():
    source = np.array([[32767 - 32768j, 3 + 4j], [-2048 + 2047j, 5 + 6j]], dtype=np.complex64)
    converted = ci16_from_complex(source)
    assert converted.dtype == np.dtype("<i2") and converted[0, 0].tolist() == [32767, -32768]
    for value in (1.5 + 2j, float("nan") + 2j, 32768 + 2j):
        bad = source.copy()
        bad[0, 0] = value
        with pytest.raises(ValueError):
            ci16_from_complex(bad)
