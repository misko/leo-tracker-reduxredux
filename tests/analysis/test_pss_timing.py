from __future__ import annotations

import hashlib

import numpy as np
import pytest

from leo.analysis.starlink import (
    PSS_NATIVE_SAMPLE_COUNT,
    PSS_NATIVE_TEMPLATE_SHA256,
    NumericalStatus,
    PssTimingSearchConfig,
    pss_native_time_samples,
    pss_subband_template,
    search_pss_frame_timing,
)
from leo.analysis.starlink.pss_timing import _normalized_match_power


def test_published_native_pss_construction_is_exact_and_immutable() -> None:
    samples = pss_native_time_samples()

    assert samples.shape == (PSS_NATIVE_SAMPLE_COUNT,)
    assert samples.dtype == np.dtype(np.complex64)
    assert not samples.flags.writeable
    assert hashlib.sha256(np.asarray(samples, dtype="<c8").tobytes()).hexdigest() == (
        PSS_NATIVE_TEMPLATE_SHA256
    )
    assert np.abs(samples) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("sample_rate_hz", "slice_center_offset_hz", "expected_count"),
    (
        (2_500_000.0, 115_195_312.5, 11),
        (3_072_000.0, 100_000_000.0, 14),
        (15_000_000.0, 112_382_812.5, 66),
        (20_000_000.0, 100_000_000.0, 88),
        (25_000_000.0, 100_000_000.0, 110),
    ),
)
def test_pss_projection_supports_declared_sample_rates(
    sample_rate_hz: float,
    slice_center_offset_hz: float,
    expected_count: int,
) -> None:
    first = pss_subband_template(
        sample_rate_hz,
        slice_center_offset_hz=slice_center_offset_hz,
    )
    second = pss_subband_template(
        sample_rate_hz,
        slice_center_offset_hz=slice_center_offset_hz,
    )

    assert first.shape == (expected_count,)
    assert first.dtype == np.dtype(np.complex64)
    assert np.linalg.norm(first) == pytest.approx(1.0, abs=1e-7)
    assert np.array_equal(first, second)
    assert not np.shares_memory(first, second)


@pytest.mark.parametrize(
    ("sample_rate_hz", "slice_center_offset_hz"),
    (
        (2_500_000.0, 115_195_312.5),
        (3_072_000.0, 100_000_000.0),
        (15_000_000.0, 112_382_812.5),
        (20_000_000.0, 100_000_000.0),
        (25_000_000.0, 100_000_000.0),
    ),
)
def test_search_recovers_frame_epoch_cfo_and_every_window_at_each_rate(
    sample_rate_hz: float,
    slice_center_offset_hz: float,
) -> None:
    template = pss_subband_template(
        sample_rate_hz,
        slice_center_offset_hz=slice_center_offset_hz,
    )
    frame_period_samples = sample_rate_hz / 750.0
    epoch_sample = round(0.00037 * sample_rate_hz)
    sample_count = round(0.040 * sample_rate_hz)
    frequency_offset_hz = 125_000.0
    rng = np.random.default_rng(194)
    values = np.asarray(
        rng.normal(size=sample_count) + 1j * rng.normal(size=sample_count),
        dtype=np.complex64,
    )
    conditioned = template * np.exp(
        2j * np.pi * frequency_offset_hz * np.arange(template.size) / sample_rate_hz
    )
    injected_starts = []
    for frame_index in range(100):
        start = round(epoch_sample + frame_index * frame_period_samples)
        if start + template.size > sample_count:
            break
        values[start : start + template.size] += 12.0 * conditioned
        injected_starts.append(start)

    global_start = 91_337
    result = search_pss_frame_timing(
        values,
        sample_rate_hz,
        global_device_sample_start=global_start,
        continuity_segment_index=7,
        slice_center_offset_hz=slice_center_offset_hz,
        nominal_frequency_offset_hz=0.0,
        frequency_offsets_hz=(-125_000.0, 0.0, frequency_offset_hz),
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.candidate_only
    assert not result.absolute_carrier_phase_resolved
    best = result.candidates[0]
    assert best.qualified
    assert best.epoch_sample == pytest.approx(epoch_sample, abs=1)
    assert best.frequency_offset_hz == frequency_offset_hz
    assert best.robust_z >= 6.0
    windows = tuple(
        window for window in result.windows if window.candidate_index == best.candidate_index
    )
    assert len(windows) == len(injected_starts)
    assert [window.measured_local_sample for window in windows] == pytest.approx(
        injected_starts,
        abs=1,
    )
    assert [window.global_device_sample for window in windows] == pytest.approx(
        [global_start + start for start in injected_starts],
        abs=1,
    )
    assert all(
        window.local_search_stop_sample > window.local_search_start_sample for window in windows
    )


def test_noise_returns_an_unqualified_diagnostic_candidate() -> None:
    sample_rate_hz = 2_500_000.0
    rng = np.random.default_rng(77)
    values = np.asarray(
        rng.normal(size=round(0.2 * sample_rate_hz))
        + 1j * rng.normal(size=round(0.2 * sample_rate_hz)),
        dtype=np.complex64,
    )

    result = search_pss_frame_timing(
        values,
        sample_rate_hz,
        global_device_sample_start=0,
        continuity_segment_index=0,
        slice_center_offset_hz=115_195_312.5,
        nominal_frequency_offset_hz=0.0,
    )

    assert result.status is NumericalStatus.NO_RESULT
    assert len(result.candidates) == 1
    assert not result.candidates[0].qualified
    assert result.windows == ()


def test_short_template_match_power_matches_direct_normalized_correlation() -> None:
    rng = np.random.default_rng(731)
    values = np.asarray(
        rng.normal(size=257) + 1j * rng.normal(size=257),
        dtype=np.complex64,
    )
    template = np.asarray(
        rng.normal(size=11) + 1j * rng.normal(size=11),
        dtype=np.complex64,
    )
    template /= np.linalg.norm(template)

    actual = _normalized_match_power(values, template, output_block_samples=32)
    expected = np.asarray(
        [
            abs(np.vdot(template, values[index : index + template.size])) ** 2
            / np.sum(np.abs(values[index : index + template.size]) ** 2)
            for index in range(values.size - template.size + 1)
        ],
        dtype=np.float64,
    )

    assert actual == pytest.approx(expected, rel=2e-6, abs=2e-7)
    assert not actual.flags.writeable


def test_short_continuity_segment_is_explicitly_insufficient() -> None:
    result = search_pss_frame_timing(
        np.ones(10_000, dtype=np.complex64),
        15_000_000.0,
        global_device_sample_start=40,
        continuity_segment_index=3,
        slice_center_offset_hz=112_382_812.5,
        nominal_frequency_offset_hz=0.0,
    )

    assert result.status is NumericalStatus.INSUFFICIENT
    assert result.candidates == ()
    assert result.windows == ()
    assert "fewer than" in result.reason


def test_invalid_search_domains_are_rejected() -> None:
    values = np.ones(100_000, dtype=np.complex64)

    with pytest.raises(ValueError, match="outside the native"):
        pss_subband_template(25_000_000.0, slice_center_offset_hz=115_000_000.0)
    with pytest.raises(ValueError, match="strictly inside"):
        search_pss_frame_timing(
            values,
            2_500_000.0,
            global_device_sample_start=0,
            continuity_segment_index=0,
            slice_center_offset_hz=115_195_312.5,
            nominal_frequency_offset_hz=0.0,
            frequency_offsets_hz=(1_250_000.0,),
        )
    with pytest.raises(ValueError, match="robust-z"):
        PssTimingSearchConfig(minimum_epoch_robust_z=0.0)
