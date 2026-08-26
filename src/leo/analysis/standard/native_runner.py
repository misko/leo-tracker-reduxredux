"""Validity-aware primitives for the additive Standard-native-v1 runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from leo.analysis.standard.native_windows import native_window_evidence
from leo.analysis.standard.observability import measure_power_timeline
from leo.analysis.standard.probes import build_probe_schedule
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.standard_native import (
    NativeOpportunityAccountingV1,
    NativeProbeWindowV3,
    NativeQualityReceiverV2,
    NativeWindowDisposition,
    StandardNativeNumericalWaterfallV3,
    StandardNativePowerTimelineV3,
    StandardNativeQualityV2,
    StandardNativeSourceV1,
    StandardProbeScheduleV3,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV4, StandardPowerTimelineV2
from leo.contracts.validity import DeviceAxisContentKind
from leo.domain.iq import IqBlock
from leo.pipeline.contracts import IqReader
from leo.pipeline.validity import ValidityAwareIqReader


@dataclass(frozen=True, slots=True)
class StandardNativeObservabilityResult:
    schedule: StandardProbeScheduleV3
    quality: StandardNativeQualityV2
    power: StandardNativePowerTimelineV3
    waterfall: StandardNativeNumericalWaterfallV3


def validate_standard_native_source(
    reader: ValidityAwareIqReader,
    binding: StandardPathInputBindV4,
) -> None:
    """Reject any reader not bound to the exact V4 logical IQ authority."""

    if (
        reader.sample_rate_hz != binding.sample_rate_hz
        or reader.center_frequency_hz != binding.tuned_center_frequency_hz
        or reader.sample_count != binding.logical_sample_count
        or reader.observed_sample_count != binding.observed_sample_count
        or reader.missing_sample_count != binding.missing_sample_count
        or reader.receiver_ids != (binding.receiver_id,)
        or reader.validity_inventory != binding.validity_inventory
    ):
        raise ValueError("Standard-native IQ reader disagrees with the exact V4 path binding")


def build_standard_native_probe_schedule(
    reader: ValidityAwareIqReader,
    binding: StandardPathInputBindV4,
    *,
    subwindow_ms: int,
    probe_ms: int,
    probe_offsets_ms: tuple[int, ...],
    maximum_coarse_windows: int,
) -> StandardProbeScheduleV3:
    """Retain the global schedule and classify every returned opportunity."""

    validate_standard_native_source(reader, binding)
    legacy = build_probe_schedule(
        sample_rate_hz=binding.sample_rate_hz,
        sample_count=binding.logical_sample_count,
        subwindow_ms=subwindow_ms,
        probe_ms=probe_ms,
        probe_offsets_ms=probe_offsets_ms,
        maximum_coarse_windows=maximum_coarse_windows,
    )
    opportunities = tuple(
        NativeProbeWindowV3(
            probe=probe,
            validity=native_window_evidence(
                reader.classify_window(probe.sample_start, probe.sample_count)
            ),
        )
        for probe in legacy.probes
    )
    disposition_counts = {
        disposition: sum(item.validity.disposition is disposition for item in opportunities)
        for disposition in NativeWindowDisposition
    }
    accounting = NativeOpportunityAccountingV1(
        scheduled_count=len(opportunities),
        valid_count=disposition_counts[NativeWindowDisposition.VALID],
        analyzed_count=0,
        passing_count=0,
        gap_excluded_count=disposition_counts[NativeWindowDisposition.GAP_OVERLAP],
        continuity_boundary_excluded_count=disposition_counts[
            NativeWindowDisposition.CONTINUITY_BOUNDARY
        ],
        outside_span_count=disposition_counts[NativeWindowDisposition.OUTSIDE_SPAN],
    )
    values: dict[str, Any] = {
        "source": StandardNativeSourceV1.from_path_binding(binding).model_dump(mode="json"),
        "coarse_window_ms": legacy.coarse_window_ms,
        "subwindow_ms": legacy.subwindow_ms,
        "probe_ms": legacy.probe_ms,
        "probe_offsets_ms": legacy.probe_offsets_ms,
        "maximum_coarse_windows": legacy.maximum_coarse_windows,
        "source_probe_count": legacy.source_probe_count,
        "returned_probe_count": legacy.returned_probe_count,
        "truncated_probe_count": legacy.truncated_probe_count,
        "opportunities": [item.model_dump(mode="json") for item in opportunities],
        "accounting": accounting.model_dump(mode="json"),
    }
    from leo.contracts.digests import canonical_digest

    return StandardProbeScheduleV3(
        **values,
        schedule_digest=canonical_digest(
            {
                "schema_version": 3,
                "algorithm_version": "standard-native-probe-schedule-v3",
                **values,
            }
        ),
    )


def run_standard_native_observability(
    reader: ValidityAwareIqReader,
    binding: StandardPathInputBindV4,
    *,
    quality_block_samples: int = 262_144,
    clipping_abs_threshold: int = 32_767,
    power_block_samples: int = 262_144,
    power_window_samples: int | None = None,
    waterfall_config: WaterfallConfig | None = None,
    subwindow_ms: int = 50,
    probe_ms: int = 20,
    probe_offsets_ms: tuple[int, ...] = (0, 25),
    maximum_coarse_windows: int = 120,
) -> StandardNativeObservabilityResult:
    """Execute the validity-safe additive stages shared by every native rate."""

    validate_standard_native_source(reader, binding)
    if quality_block_samples <= 0 or not 1 <= clipping_abs_threshold <= 32_768:
        raise ValueError("native quality bounds are invalid")
    source = StandardNativeSourceV1.from_path_binding(binding)
    schedule = build_standard_native_probe_schedule(
        reader,
        binding,
        subwindow_ms=subwindow_ms,
        probe_ms=probe_ms,
        probe_offsets_ms=probe_offsets_ms,
        maximum_coarse_windows=maximum_coarse_windows,
    )
    quality = _measure_native_quality(
        reader,
        source,
        receiver_id=binding.receiver_id,
        block_samples=quality_block_samples,
        clipping_abs_threshold=clipping_abs_threshold,
    )
    logical_reader = _LogicalValidIqReader(reader)
    power_document = measure_power_timeline(
        logical_reader,
        window_samples=power_window_samples,
        block_samples=power_block_samples,
    )
    power = StandardNativePowerTimelineV3(
        source=source,
        timeline=StandardPowerTimelineV2.model_validate(power_document),
    )
    from leo.analysis.standard.native_waterfall import measure_standard_native_waterfall

    waterfall = measure_standard_native_waterfall(
        reader,
        binding,
        waterfall_config or WaterfallConfig(),
    )
    return StandardNativeObservabilityResult(
        schedule=schedule,
        quality=quality,
        power=power,
        waterfall=waterfall,
    )


class _LogicalValidIqReader:
    """Project truthful segment readers onto global logical sample coordinates."""

    def __init__(self, source: ValidityAwareIqReader) -> None:
        self._source = source

    @property
    def sample_rate_hz(self) -> int:
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._source.sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self._source.receiver_ids

    def iter_blocks(self, *, block_samples: int):
        previous_global_stop = 0
        for segment_reader in self._source.segment_readers():
            if segment_reader.receiver_ids != self.receiver_ids:
                raise ValueError("native segment receiver inventory changed")
            for block in segment_reader.iter_blocks(block_samples=block_samples):
                local_start = block.metadata.session_sample_start
                global_start = segment_reader.to_global_device_sample(local_start)
                if global_start < previous_global_stop:
                    raise ValueError("native segment blocks overlap or regress globally")
                global_stop = global_start + block.metadata.sample_count
                if global_stop > segment_reader.segment.device_sample_stop:
                    raise ValueError("native segment block exceeds its authoritative extent")
                previous_global_stop = global_stop
                yield IqBlock(
                    samples=block.samples,
                    metadata=block.metadata.model_copy(
                        update={"session_sample_start": global_start}
                    ),
                )


def _measure_native_quality(
    reader: ValidityAwareIqReader,
    source: StandardNativeSourceV1,
    *,
    receiver_id: int,
    block_samples: int,
    clipping_abs_threshold: int,
) -> StandardNativeQualityV2:
    valid_count = 0
    energy_sum = 0
    clipped_components = 0
    clipped_samples = 0
    minimum: np.ndarray | None = None
    maximum: np.ndarray | None = None
    for span in reader.iter_valid_blocks(block_samples=block_samples):
        if span.receiver_ids != (receiver_id,) or not np.all(span.valid_samples):
            raise ValueError("native valid-block iterator returned foreign or invalid IQ")
        values = span.samples[:, 0, :].astype(np.int64, copy=False)
        magnitudes = np.abs(values)
        valid_count += span.sample_count
        energy_sum += int(np.sum(values * values, dtype=np.int64))
        clipped_components += int(np.count_nonzero(magnitudes >= clipping_abs_threshold))
        clipped_samples += int(
            np.count_nonzero(np.any(magnitudes >= clipping_abs_threshold, axis=1))
        )
        block_minimum = values.min(axis=0)
        block_maximum = values.max(axis=0)
        minimum = block_minimum if minimum is None else np.minimum(minimum, block_minimum)
        maximum = block_maximum if maximum is None else np.maximum(maximum, block_maximum)
    if valid_count != source.observed_sample_count:
        raise ValueError("native valid-block iterator did not close observed IQ")
    uncovered = sum(
        item.content_kind is DeviceAxisContentKind.ZERO_FILL
        for item in reader.validity_inventory.runs
    )
    assert minimum is not None and maximum is not None
    receiver = NativeQualityReceiverV2(
        receiver_id=receiver_id,
        valid_sample_count=valid_count,
        energy_sum_ci16_squared=energy_sum,
        clipped_component_count=clipped_components,
        clipped_complex_sample_count=clipped_samples,
        clipped_complex_fraction=clipped_samples / valid_count,
        constant_iq=bool(np.array_equal(minimum, maximum)),
        minimum_i=int(minimum[0]),
        maximum_i=int(maximum[0]),
        minimum_q=int(minimum[1]),
        maximum_q=int(maximum[1]),
    )
    return StandardNativeQualityV2(
        source=source,
        clipping_abs_threshold=clipping_abs_threshold,
        uncovered_region_count=uncovered,
        receivers=(receiver,),
    )


def as_iq_reader(reader: ValidityAwareIqReader) -> IqReader:
    """Expose the reviewed valid-only logical projection to additive kernels."""

    return _LogicalValidIqReader(reader)
