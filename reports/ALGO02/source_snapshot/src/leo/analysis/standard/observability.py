"""Bounded one-receiver observability products for Standard analysis."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

import numpy as np

from leo.analysis._streaming import validated_blocks
from leo.analysis.waterfall import WaterfallConfig, WaterfallResult
from leo.contracts.standard_pipeline import (
    StandardNumericalWaterfallV2,
    StandardPowerTimelineV2,
)
from leo.pipeline import IqReader

_CI16_SCALE_SQUARED = 32_768**2


def measure_power_timeline(
    reader: IqReader,
    *,
    window_samples: int | None = None,
    block_samples: int = 262_144,
    maximum_windows: int = 3_600,
) -> dict[str, Any]:
    """Compute a real bounded power time series in CI16 dBFS units."""

    if len(reader.receiver_ids) != 1:
        raise ValueError("power timeline requires exactly one receiver")
    window = reader.sample_rate_hz if window_samples is None else window_samples
    if window <= 0 or block_samples <= 0 or maximum_windows <= 0:
        raise ValueError("power timeline bounds must be positive")
    source_window_count = math.ceil(reader.sample_count / window) if reader.sample_count else 0
    returned_window_count = min(source_window_count, maximum_windows)
    sums = np.zeros(returned_window_count, dtype=np.float64)
    counts = np.zeros(returned_window_count, dtype=np.int64)
    observed = 0
    uncovered_regions = 0
    cursor = 0
    maximum_temporary_bytes = 0
    for block in validated_blocks(reader, block_samples=block_samples):
        start = block.metadata.session_sample_start
        if start > cursor:
            uncovered_regions += 1
        cursor = start + block.metadata.sample_count
        observed += block.metadata.sample_count
        widened = block.samples[:, 0, :].astype(np.int64, copy=False)
        power = np.sum(widened * widened, axis=1, dtype=np.int64)
        # ``widened`` is an allocated int64 conversion for native CI16 and the
        # multiply allocates another matrix before the reduced power vector.
        multiply_bytes = widened.nbytes
        maximum_temporary_bytes = max(
            maximum_temporary_bytes,
            widened.nbytes + multiply_bytes + power.nbytes,
        )
        local = 0
        while local < len(power):
            absolute = start + local
            bin_index = absolute // window
            next_boundary = min(len(power), (bin_index + 1) * window - start)
            if bin_index < returned_window_count:
                sums[bin_index] += float(np.sum(power[local:next_boundary], dtype=np.int64))
                counts[bin_index] += next_boundary - local
            local = next_boundary
    if cursor < reader.sample_count:
        uncovered_regions += 1
    timeline = []
    for index in range(returned_window_count):
        sample_start = index * window
        sample_stop = min(reader.sample_count, sample_start + window)
        linear = sums[index] / (int(counts[index]) * _CI16_SCALE_SQUARED) if counts[index] else None
        timeline.append(
            {
                "window_index": index,
                "sample_start": sample_start,
                "sample_stop": sample_stop,
                "time_start_s": sample_start / reader.sample_rate_hz,
                "time_stop_s": sample_stop / reader.sample_rate_hz,
                "observed_sample_count": int(counts[index]),
                "mean_power_full_scale_squared": linear,
                "mean_power_dbfs": (
                    10.0 * math.log10(linear) if linear is not None and linear > 0 else None
                ),
            }
        )
    missing = reader.sample_count - observed
    document = {
        "schema_version": 2,
        "algorithm_version": "bounded-power-timeline-v2",
        "sample_rate_hz": reader.sample_rate_hz,
        "expected_sample_count": reader.sample_count,
        "observed_sample_count": observed,
        "missing_sample_count": missing,
        "coverage_fraction": observed / reader.sample_count if reader.sample_count else 0.0,
        "uncovered_region_count": uncovered_regions,
        "receiver_ids": list(reader.receiver_ids),
        "normalization": "E[I^2+Q^2]/32768^2",
        "logarithmic_unit": "dBFS",
        "window_samples": window,
        "source_window_count": source_window_count,
        "returned_window_count": returned_window_count,
        "truncated_window_count": source_window_count - returned_window_count,
        "timeline": timeline,
        "maximum_working_set_bytes": max(1, sums.nbytes + counts.nbytes + maximum_temporary_bytes),
    }
    return StandardPowerTimelineV2.model_validate(document).model_dump(mode="json")


def numerical_waterfall_document(
    result: WaterfallResult,
    config: WaterfallConfig,
) -> dict[str, Any]:
    """Wrap the numerical kernel in its additive closed Standard-v2 contract."""

    values = asdict(result)
    document = {
        "schema_version": 2,
        "algorithm_version": "standard-numerical-waterfall-v2",
        "kernel_algorithm_version": values["algorithm_version"],
        "config_digest": values["config_digest"],
        "sample_rate_hz": values["sample_rate_hz"],
        "fft_samples": config.fft_samples,
        "frequency_bin_count": len(values["frequency_bin_centers_hz"]),
        "time_bin_count": len(values["tiles"]),
        "receiver_ids": values["receiver_ids"],
        "frequency_bin_centers_hz": values["frequency_bin_centers_hz"],
        "coverage": values["coverage"],
        "tiles": values["tiles"],
        "maximum_working_set_bytes": values["maximum_working_set_bytes"],
    }
    return StandardNumericalWaterfallV2.model_validate(document).model_dump(mode="json")
