from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pytest

from leo.analysis.standard.observability import (
    measure_power_timeline,
    numerical_waterfall_document,
)
from leo.analysis.waterfall import WaterfallConfig, bounded_waterfall
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.standard_pipeline import (
    StandardNumericalWaterfallV2,
    StandardPowerTimelineV2,
)
from leo.domain.iq import IqBlock


def test_power_v2_accounts_for_tail_gaps_and_every_new_array() -> None:
    complete = _Reader(
        sample_rate_hz=4,
        sample_count=10,
        blocks=((0, np.full((10, 1, 2), (3, 4), dtype="<i2")),),
    )

    tail = StandardPowerTimelineV2.model_validate(
        measure_power_timeline(complete, window_samples=4, block_samples=10)
    )

    assert tuple(item.observed_sample_count for item in tail.timeline) == (4, 4, 2)
    assert tuple(item.sample_stop for item in tail.timeline) == (4, 8, 10)
    assert all(item.mean_power_full_scale_squared is not None for item in tail.timeline)
    # sums + counts + int64 IQ + multiply temporary + reduced power vector
    minimum_accounted = 3 * 8 + 3 * 8 + 10 * 2 * 8 + 10 * 2 * 8 + 10 * 8
    assert tail.maximum_working_set_bytes >= minimum_accounted

    gap_reader = _Reader(
        sample_rate_hz=8,
        sample_count=8,
        blocks=(
            (0, np.ones((3, 1, 2), dtype="<i2")),
            (5, np.ones((3, 1, 2), dtype="<i2")),
        ),
    )
    gap = StandardPowerTimelineV2.model_validate(
        measure_power_timeline(gap_reader, window_samples=8, block_samples=8)
    )

    assert gap.observed_sample_count == 6
    assert gap.missing_sample_count == 2
    assert gap.coverage_fraction == pytest.approx(0.75)
    assert gap.uncovered_region_count == 1
    assert gap.timeline[0].observed_sample_count == 6


def test_numerical_waterfall_v2_places_tone_and_bounds_noise_working_set() -> None:
    sample_rate = 1_024
    sample_count = 1_024
    time = np.arange(sample_count, dtype=np.float64) / sample_rate
    tone = 12_000 * np.exp(2j * np.pi * 128.0 * time)
    reader = _Reader.from_complex(tone, sample_rate_hz=sample_rate)
    config = WaterfallConfig(
        fft_samples=128,
        frequency_bins=128,
        maximum_time_bins=2,
        block_samples=256,
    )

    result = bounded_waterfall(reader, config)
    document = StandardNumericalWaterfallV2.model_validate(
        numerical_waterfall_document(result, config)
    )
    average = np.mean(
        np.asarray(
            [tile.receiver_power_dbfs[0] for tile in document.tiles],
            dtype=np.float64,
        ),
        axis=0,
    )
    peak_hz = document.frequency_bin_centers_hz[int(np.argmax(average))]

    assert peak_hz == pytest.approx(128.0)
    assert document.coverage.observed_fraction == 1.0
    assert document.coverage.transformed_fraction == 1.0
    assert document.maximum_working_set_bytes > 10 * reader.maximum_block_bytes

    generator = np.random.default_rng(0x51A7)
    noise = generator.integers(-500, 501, size=(1_024, 1, 2), dtype=np.int16)
    noise_reader = _Reader(
        sample_rate_hz=sample_rate,
        sample_count=sample_count,
        blocks=((0, noise),),
    )
    noise_document = numerical_waterfall_document(bounded_waterfall(noise_reader, config), config)
    assert all(
        value is None or np.isfinite(value)
        for tile in noise_document["tiles"]
        for row in tile["receiver_power_dbfs"]
        for value in row
    )


@dataclass
class _Reader:
    sample_rate_hz: int
    sample_count: int
    blocks: tuple[tuple[int, np.ndarray], ...]
    center_frequency_hz: int = 1_000_000
    receiver_ids: tuple[int, ...] = (0,)
    maximum_block_bytes: int = 0

    @classmethod
    def from_complex(cls, samples: np.ndarray, *, sample_rate_hz: int) -> _Reader:
        values = np.empty((len(samples), 1, 2), dtype="<i2")
        values[:, 0, 0] = np.rint(samples.real).astype("<i2")
        values[:, 0, 1] = np.rint(samples.imag).astype("<i2")
        return cls(sample_rate_hz, len(values), ((0, values),))

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        for source_start, source_values in self.blocks:
            for offset in range(0, len(source_values), block_samples):
                values = np.ascontiguousarray(source_values[offset : offset + block_samples])
                self.maximum_block_bytes = max(self.maximum_block_bytes, values.nbytes)
                start = source_start + offset
                interval = NanosecondIntervalV1(lower_ns=start, upper_ns=start)
                yield IqBlock(
                    samples=values,
                    metadata=IqBlockMetadataV1(
                        radio_id="fixture-radio",
                        receiver_ids=self.receiver_ids,
                        sample_count=len(values),
                        session_sample_start=start,
                        host_request_utc_ns=interval,
                        host_request_monotonic_ns=interval,
                    ),
                )
