"""Segment-reset numerical waterfall for Standard-native-v1."""

from __future__ import annotations

import math

import numpy as np

from leo.analysis.standard.native_windows import StandardNativeWindowAdapter
from leo.analysis.standard.observability import numerical_waterfall_document
from leo.analysis.waterfall import (
    WaterfallConfig,
    WaterfallCoverage,
    WaterfallResult,
    WaterfallTile,
)
from leo.contracts.standard_native import (
    StandardNativeNumericalWaterfallV3,
    StandardNativeSourceV1,
)
from leo.contracts.standard_pipeline import StandardNumericalWaterfallV2, StandardPathInputBindV4
from leo.pipeline.validity import ValidityAwareIqReader


def measure_standard_native_waterfall(
    reader: ValidityAwareIqReader,
    binding: StandardPathInputBindV4,
    config: WaterfallConfig,
) -> StandardNativeNumericalWaterfallV3:
    """Transform only complete per-segment FFT windows on the global time axis."""

    from leo.analysis.standard.native_runner import validate_standard_native_source

    validate_standard_native_source(reader, binding)
    receiver_count = len(reader.receiver_ids)
    time_bins = min(config.maximum_time_bins, max(reader.sample_count, 1))
    samples_per_time_bin = max(1, math.ceil(max(reader.sample_count, 1) / time_bins))
    sums = np.zeros((time_bins, receiver_count, config.frequency_bins), dtype=np.float64)
    counts = np.zeros(time_bins, dtype=np.int64)
    window = np.hanning(config.fft_samples).astype(np.float64)
    window_energy = float(np.sum(window**2))
    groups = tuple(
        np.asarray(group, dtype=np.int64)
        for group in np.array_split(np.arange(config.fft_samples), config.frequency_bins)
    )
    raw_frequencies = np.fft.fftshift(
        np.fft.fftfreq(config.fft_samples, d=1 / reader.sample_rate_hz)
    )
    frequency_centers = tuple(float(np.mean(raw_frequencies[group])) for group in groups)
    observed = 0
    transformed = 0
    maximum_block = 0
    maximum_intermediate = 0

    window_adapter = StandardNativeWindowAdapter(reader)
    for segment_input in window_adapter.segment_inputs:
        segment_reader = segment_input.iq
        if segment_reader is None:
            # Empty terminal segments still occur in the reset inventory but
            # contain no complete transform support.
            continue
        carry = np.empty((0, receiver_count, 2), dtype="<i2")
        carry_local_start = 0
        expected_local_start = 0
        for block in segment_reader.iter_blocks(block_samples=config.block_samples):
            local_start = block.metadata.session_sample_start
            if local_start != expected_local_start:
                raise ValueError("native waterfall segment reader is not locally contiguous")
            expected_local_start += block.metadata.sample_count
            observed += block.metadata.sample_count
            maximum_block = max(maximum_block, block.samples.nbytes)
            if carry.size:
                values = np.concatenate((carry, block.samples), axis=0)
                values_local_start = carry_local_start
                concatenated_bytes = values.nbytes
            else:
                values = block.samples
                values_local_start = local_start
                concatenated_bytes = 0
            offset = 0
            while offset + config.fft_samples <= len(values):
                frame_count = min(16, (len(values) - offset) // config.fft_samples)
                sample_count = frame_count * config.fft_samples
                iq = values[offset : offset + sample_count].reshape(
                    frame_count,
                    config.fft_samples,
                    receiver_count,
                    2,
                )
                complex_values = (
                    iq[:, :, :, 0].astype(np.float64) + 1j * iq[:, :, :, 1].astype(np.float64)
                ) / 32_768.0
                spectrum = np.fft.fftshift(
                    np.fft.fft(complex_values * window[None, :, None], axis=1),
                    axes=(1,),
                )
                power = np.abs(spectrum) ** 2 / (config.fft_samples * window_energy)
                grouped = np.stack(
                    tuple(np.sum(power[:, group, :], axis=1) for group in groups),
                    axis=1,
                )
                local_starts = (
                    values_local_start
                    + offset
                    + np.arange(frame_count, dtype=np.int64) * config.fft_samples
                )
                absolute_starts = local_starts + segment_reader.global_device_sample_start
                batch_bins = np.minimum(
                    absolute_starts // samples_per_time_bin,
                    time_bins - 1,
                )
                maximum_intermediate = max(
                    maximum_intermediate,
                    concatenated_bytes
                    + 3 * complex_values.nbytes
                    + 2 * spectrum.nbytes
                    + 2 * power.nbytes
                    + 2 * grouped.nbytes
                    + local_starts.nbytes
                    + absolute_starts.nbytes
                    + batch_bins.nbytes,
                )
                for time_bin in np.unique(batch_bins):
                    selected = batch_bins == time_bin
                    sums[time_bin] += np.sum(grouped[selected], axis=0).T
                    counts[time_bin] += int(np.count_nonzero(selected))
                transformed += sample_count
                offset += sample_count
            carry = np.ascontiguousarray(values[offset:])
            carry_local_start = values_local_start + offset
        if expected_local_start != segment_reader.sample_count:
            raise ValueError("native waterfall segment reader ended before its declaration")

    if observed != reader.observed_sample_count:
        raise ValueError("native waterfall segment inventory did not close observed IQ")
    tiles = []
    for time_bin in range(time_bins):
        start = time_bin * samples_per_time_bin
        stop = min(reader.sample_count, start + samples_per_time_bin)
        rows: list[tuple[float | None, ...]] = []
        for receiver in range(receiver_count):
            row = tuple(
                None
                if counts[time_bin] == 0
                else max(
                    config.floor_dbfs,
                    10
                    * math.log10(
                        max(
                            sums[time_bin, receiver, frequency_bin] / counts[time_bin],
                            1e-300,
                        )
                    ),
                )
                for frequency_bin in range(config.frequency_bins)
            )
            rows.append(row)
        tiles.append(
            WaterfallTile(
                time_bin=time_bin,
                sample_start=start,
                sample_stop=stop,
                transform_count=int(counts[time_bin]),
                receiver_power_dbfs=tuple(rows),
            )
        )
    persistent_bytes = (
        sums.nbytes
        + counts.nbytes
        + window.nbytes
        + raw_frequencies.nbytes
        + sum(group.nbytes for group in groups)
    )
    carry_bound = config.fft_samples * receiver_count * 2 * np.dtype("<i2").itemsize
    result = WaterfallResult(
        algorithm_version="bounded-waterfall-v1",
        config_digest=config.digest,
        sample_rate_hz=reader.sample_rate_hz,
        receiver_ids=reader.receiver_ids,
        frequency_bin_centers_hz=frequency_centers,
        coverage=WaterfallCoverage(
            expected_samples=reader.sample_count,
            observed_samples=observed,
            transformed_samples=transformed,
            missing_samples=reader.missing_sample_count,
            gap_count=max(0, len(reader.validity_inventory.segments) - 1),
            observed_fraction=observed / reader.sample_count,
            transformed_fraction=transformed / reader.sample_count,
        ),
        tiles=tuple(tiles),
        maximum_working_set_bytes=(
            maximum_block + carry_bound + persistent_bytes + maximum_intermediate
        ),
    )
    document = numerical_waterfall_document(result, config)
    return StandardNativeNumericalWaterfallV3(
        source=StandardNativeSourceV1.from_path_binding(binding),
        waterfall=StandardNumericalWaterfallV2.model_validate(document),
    )
