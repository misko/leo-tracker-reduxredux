"""Bounded-memory waterfall tiles for arbitrarily long CI16 dwells."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from leo.analysis._streaming import validated_blocks
from leo.contracts.digests import canonical_digest
from leo.pipeline import IqReader


@dataclass(frozen=True, slots=True)
class WaterfallConfig:
    fft_samples: int = 1024
    frequency_bins: int = 128
    maximum_time_bins: int = 256
    block_samples: int = 262_144
    floor_dbfs: float = -160.0

    def __post_init__(self) -> None:
        if self.fft_samples < 16 or self.fft_samples > 1_048_576:
            raise ValueError("fft_samples must be between 16 and 1048576")
        if self.frequency_bins < 1 or self.frequency_bins > self.fft_samples:
            raise ValueError("frequency_bins must lie in 1..fft_samples")
        if self.maximum_time_bins < 1 or self.maximum_time_bins > 16_384:
            raise ValueError("maximum_time_bins must lie in 1..16384")
        if self.block_samples < self.fft_samples or self.block_samples > 4_194_304:
            raise ValueError("block_samples must contain at least one bounded FFT")
        if not math.isfinite(self.floor_dbfs) or self.floor_dbfs >= 0:
            raise ValueError("floor_dbfs must be finite and negative")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class WaterfallCoverage:
    expected_samples: int
    observed_samples: int
    transformed_samples: int
    missing_samples: int
    gap_count: int
    observed_fraction: float
    transformed_fraction: float


@dataclass(frozen=True, slots=True)
class WaterfallTile:
    time_bin: int
    sample_start: int
    sample_stop: int
    transform_count: int
    receiver_power_dbfs: tuple[tuple[float | None, ...], ...]


@dataclass(frozen=True, slots=True)
class WaterfallResult:
    algorithm_version: str
    config_digest: str
    sample_rate_hz: int
    receiver_ids: tuple[int, ...]
    frequency_bin_centers_hz: tuple[float, ...]
    coverage: WaterfallCoverage
    tiles: tuple[WaterfallTile, ...]
    maximum_working_set_bytes: int


def bounded_waterfall(reader: IqReader, config: WaterfallConfig) -> WaterfallResult:
    """Stream one dwell into a fixed time/frequency tile budget.

    FFT windows never cross a declared gap. At most one reader block, one FFT
    carry, and the bounded output accumulators are resident at once.
    """

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
    uniform_group_size = (
        config.fft_samples // config.frequency_bins
        if config.fft_samples % config.frequency_bins == 0
        else None
    )
    raw_frequencies = np.fft.fftshift(
        np.fft.fftfreq(config.fft_samples, d=1 / reader.sample_rate_hz)
    )
    frequency_centers = tuple(float(np.mean(raw_frequencies[group])) for group in groups)
    carry = np.empty((0, receiver_count, 2), dtype="<i2")
    carry_start = 0
    expected_next = 0
    observed = 0
    transformed = 0
    gaps = 0
    maximum_block = 0
    maximum_intermediate = 0

    for block in validated_blocks(reader, block_samples=config.block_samples):
        start = block.metadata.session_sample_start
        maximum_block = max(maximum_block, block.samples.nbytes)
        observed += block.metadata.sample_count
        if start != expected_next:
            if start > expected_next:
                gaps += 1
            carry = np.empty((0, receiver_count, 2), dtype="<i2")
            carry_start = start
        if carry.size:
            values = np.concatenate((carry, block.samples), axis=0)
            values_start = carry_start
            concatenated_bytes = values.nbytes
        else:
            values = block.samples
            values_start = start
            concatenated_bytes = 0
        offset = 0
        while offset + config.fft_samples <= len(values):
            frame_count = min(16, (len(values) - offset) // config.fft_samples)
            sample_count = frame_count * config.fft_samples
            iq = values[offset : offset + sample_count].reshape(
                frame_count, config.fft_samples, receiver_count, 2
            )
            complex_values = (
                iq[:, :, :, 0].astype(np.float64) + 1j * iq[:, :, :, 1].astype(np.float64)
            ) / 32_768.0
            windowed_bytes = complex_values.nbytes
            spectrum = np.fft.fftshift(
                np.fft.fft(complex_values * window[None, :, None], axis=1),
                axes=(1,),
            )
            power = np.abs(spectrum) ** 2 / (config.fft_samples * window_energy)
            grouped = (
                np.sum(
                    power.reshape(
                        frame_count,
                        config.frequency_bins,
                        uniform_group_size,
                        receiver_count,
                    ),
                    axis=2,
                )
                if uniform_group_size is not None
                else np.stack(
                    tuple(np.sum(power[:, group, :], axis=1) for group in groups),
                    axis=1,
                )
            )
            absolute_starts = (
                values_start + offset + np.arange(frame_count, dtype=np.int64) * config.fft_samples
            )
            batch_bins = np.minimum(absolute_starts // samples_per_time_bin, time_bins - 1)
            # Conservative peak: account for every newly allocated array in
            # this vector batch, including expression temporaries and the
            # tuple-of-groups plus its stacked copy. Views such as ``iq`` and
            # the reader-owned block are accounted by their owning buffers.
            grouped_pair_bytes = grouped.nbytes * 2
            spectrum_pair_bytes = spectrum.nbytes * 2
            power_pair_bytes = power.nbytes * 2
            batch_index_bytes = absolute_starts.nbytes + batch_bins.nbytes
            maximum_intermediate = max(
                maximum_intermediate,
                concatenated_bytes
                # Two component conversions, complex construction and its
                # normalized result can coexist while evaluating the IQ
                # expression; all are distinct allocations.
                + 3 * complex_values.nbytes
                + windowed_bytes
                + spectrum_pair_bytes
                + power_pair_bytes
                + grouped_pair_bytes
                + batch_index_bytes
                + frame_count * np.dtype(np.bool_).itemsize,
            )
            for time_bin in np.unique(batch_bins):
                selected = batch_bins == time_bin
                sums[time_bin] += np.sum(grouped[selected], axis=0).T
                counts[time_bin] += int(np.count_nonzero(selected))
            transformed += sample_count
            offset += sample_count
        carry = np.ascontiguousarray(values[offset:])
        carry_start = values_start + offset
        expected_next = start + block.metadata.sample_count

    if expected_next < reader.sample_count:
        gaps += 1
    missing = reader.sample_count - observed
    tiles = []
    for time_bin in range(time_bins):
        start = time_bin * samples_per_time_bin
        stop = min(reader.sample_count, start + samples_per_time_bin)
        receiver_rows: list[tuple[float | None, ...]] = []
        for receiver in range(receiver_count):
            row: list[float | None] = []
            for frequency_bin in range(config.frequency_bins):
                if counts[time_bin] == 0:
                    row.append(None)
                    continue
                linear = sums[time_bin, receiver, frequency_bin] / counts[time_bin]
                row.append(max(config.floor_dbfs, 10 * math.log10(max(linear, 1e-300))))
            receiver_rows.append(tuple(row))
        tiles.append(
            WaterfallTile(
                time_bin,
                start,
                stop,
                int(counts[time_bin]),
                tuple(receiver_rows),
            )
        )
    group_index_bytes = sum(group.nbytes for group in groups)
    persistent_bytes = (
        sums.nbytes + counts.nbytes + window.nbytes + raw_frequencies.nbytes + group_index_bytes
    )
    carry_bound = config.fft_samples * receiver_count * 2 * np.dtype("<i2").itemsize
    return WaterfallResult(
        algorithm_version="bounded-waterfall-v1",
        config_digest=config.digest,
        sample_rate_hz=reader.sample_rate_hz,
        receiver_ids=reader.receiver_ids,
        frequency_bin_centers_hz=frequency_centers,
        coverage=WaterfallCoverage(
            expected_samples=reader.sample_count,
            observed_samples=observed,
            transformed_samples=transformed,
            missing_samples=missing,
            gap_count=gaps,
            observed_fraction=observed / reader.sample_count if reader.sample_count else 0.0,
            transformed_fraction=(
                transformed / reader.sample_count if reader.sample_count else 0.0
            ),
        ),
        tiles=tuple(tiles),
        maximum_working_set_bytes=(
            maximum_block + carry_bound + persistent_bytes + maximum_intermediate
        ),
    )
