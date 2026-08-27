from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
import pytest

from leo.analysis.standard.native_runner import run_standard_native_observability
from leo.contracts.digests import canonical_digest
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.validity import ContinuitySegmentV1, ValidityInventoryV1
from leo.domain.iq import IqBlock
from leo.pipeline.validity import DeviceIqSpan, WindowClassification, WindowValidity

_CENTER_HZ = 959_687_500
_TONE_HZ = 50_000
_AMPLITUDE = 8_192


def _metadata(sample_start: int, sample_count: int) -> IqBlockMetadataV1:
    return IqBlockMetadataV1(
        radio_id="radio-0",
        receiver_ids=(0,),
        sample_count=sample_count,
        session_sample_start=sample_start,
        host_request_utc_ns=NanosecondIntervalV1(lower_ns=1, upper_ns=1),
        host_request_monotonic_ns=NanosecondIntervalV1(lower_ns=1, upper_ns=1),
    )


def _tone(sample_rate_hz: int, start: int, count: int) -> np.ndarray:
    indexes = start + np.arange(count, dtype=np.float64)
    phase = 2.0 * math.pi * _TONE_HZ * indexes / sample_rate_hz
    values = np.empty((count, 1, 2), dtype="<i2")
    values[:, 0, 0] = np.rint(_AMPLITUDE * np.cos(phase)).astype("<i2")
    values[:, 0, 1] = np.rint(_AMPLITUDE * np.sin(phase)).astype("<i2")
    return values


class _ToneSegmentReader:
    def __init__(self, sample_rate_hz: int, segment: ContinuitySegmentV1) -> None:
        self._sample_rate_hz = sample_rate_hz
        self.segment = segment

    @property
    def continuity_segment_index(self) -> int:
        return self.segment.segment_index

    @property
    def global_device_sample_start(self) -> int:
        return self.segment.device_sample_start

    @property
    def sample_rate_hz(self) -> int:
        return self._sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return _CENTER_HZ

    @property
    def sample_count(self) -> int:
        return self.segment.observed_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (0,)

    def to_global_device_sample(self, local_sample: int) -> int:
        return self.global_device_sample_start + local_sample

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        for start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - start)
            yield IqBlock(
                samples=_tone(
                    self.sample_rate_hz,
                    self.global_device_sample_start + start,
                    count,
                ),
                metadata=_metadata(start, count),
            )


class _ToneReader:
    def __init__(self, sample_rate_hz: int, inventory: ValidityInventoryV1) -> None:
        self.sample_rate_hz = sample_rate_hz
        self.sample_count = sample_rate_hz
        self.observed_sample_count = sample_rate_hz
        self.missing_sample_count = 0
        self.validity_inventory = inventory

    center_frequency_hz = _CENTER_HZ
    receiver_ids = (0,)

    def segment_readers(self) -> tuple[_ToneSegmentReader, ...]:
        return tuple(
            _ToneSegmentReader(self.sample_rate_hz, segment)
            for segment in self.validity_inventory.segments
        )

    def iter_valid_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        for start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - start)
            yield DeviceIqSpan(
                samples=_tone(self.sample_rate_hz, start, count),
                valid_samples=np.ones(count, dtype=np.bool_),
                continuity_segment_ids=np.zeros(count, dtype=np.int32),
                device_sample_start=start,
                receiver_ids=(0,),
            )

    def iter_masked_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        return self.iter_valid_blocks(block_samples=block_samples)

    def read_device_span(self, device_sample_start: int, sample_count: int) -> DeviceIqSpan:
        return DeviceIqSpan(
            samples=_tone(self.sample_rate_hz, device_sample_start, sample_count),
            valid_samples=np.ones(sample_count, dtype=np.bool_),
            continuity_segment_ids=np.zeros(sample_count, dtype=np.int32),
            device_sample_start=device_sample_start,
            receiver_ids=(0,),
        )

    def classify_window(
        self,
        device_sample_start: int,
        sample_count: int,
    ) -> WindowClassification:
        if device_sample_start < 0 or device_sample_start + sample_count > self.sample_count:
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.OUTSIDE_SPAN,
            )
        return WindowClassification(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            status=WindowValidity.VALID,
            continuity_segment_index=0,
        )

    def close(self) -> None:
        pass


def _inventory(sample_rate_hz: int) -> ValidityInventoryV1:
    return ValidityInventoryV1.model_validate(
        {
            "stream_id": "stream-0",
            "timeline_sha256": canonical_digest({"timeline": sample_rate_hz}),
            "gap_map_content_digest": canonical_digest({"gap-map": sample_rate_hz}),
            "first_device_sample_counter": 100,
            "logical_sample_count": sample_rate_hz,
            "observed_sample_count": sample_rate_hz,
            "missing_sample_count": 0,
            "continuity_boundary_count": 0,
            "runs": [
                {
                    "run_index": 0,
                    "device_sample_start": 0,
                    "sample_count": sample_rate_hz,
                    "content_kind": "observed",
                    "stored_sample_start": 0,
                    "continuity_segment_index": 0,
                },
            ],
            "segments": [
                {
                    "segment_index": 0,
                    "device_sample_start": 0,
                    "device_sample_stop": sample_rate_hz,
                    "stored_sample_start": 0,
                    "stored_sample_stop": sample_rate_hz,
                },
            ],
        }
    )


def _binding(sample_rate_hz: int, inventory: ValidityInventoryV1) -> StandardPathInputBindV4:
    values = {
        "schema_version": 4,
        "algorithm_version": "standard-path-input-bind-v4",
        "session_id": "session-1",
        "stream_id": "stream-0",
        "radio_id": "radio-0",
        "receiver_id": 0,
        "manifest_digest": canonical_digest({"manifest": 1}),
        "raw_integrity_attestation_digest": canonical_digest({"integrity": 1}),
        "selected_stream_digest": canonical_digest({"stream": 1}),
        "compressed_chunk_closure_digest": canonical_digest({"compressed": 1}),
        "uncompressed_chunk_closure_digest": canonical_digest({"uncompressed": 1}),
        "synchronization_inventory_digest": canonical_digest({"sync": 1}),
        "profile_revision_digest": canonical_digest({"profile": sample_rate_hz}),
        "capture_plan_digest": canonical_digest({"plan": sample_rate_hz}),
        "receiver_settings_digest": canonical_digest({"settings": sample_rate_hz}),
        "science_configuration_digest": canonical_digest({"configuration": sample_rate_hz}),
        "science_implementation_digest": canonical_digest({"implementation": 1}),
        "capture_lineage_resolution": "resolved",
        "physical_receiver_id": "physical-rx-0",
        "hardware_epoch_id": "epoch-1",
        "tuned_center_frequency_hz": _CENTER_HZ,
        "sample_rate_hz": sample_rate_hz,
        "declared_sample_count": sample_rate_hz,
        "starlink_channel": 1,
        "starlink_edge": "lower",
        "starlink_tuning_evidence_source": "capture_profile",
        "rf_bandwidth_hz": 2_500_000,
        "requested_sample_count": sample_rate_hz,
        "requested_duration_seconds": "1",
        "logical_sample_count": sample_rate_hz,
        "observed_sample_count": sample_rate_hz,
        "missing_sample_count": 0,
        "observed_iq_digest": canonical_digest({"iq": sample_rate_hz}),
        "logical_iq_digest": canonical_digest({"iq": sample_rate_hz}),
        "timeline_sha256": inventory.timeline_sha256,
        "gap_map_sha256": canonical_digest({"gap-map-file": sample_rate_hz}),
        "gap_map_content_digest": inventory.gap_map_content_digest,
        "validity_inventory_sha256": inventory.inventory_digest,
        "first_device_sample_counter": 100,
        "last_device_sample_counter_inclusive": 99 + sample_rate_hz,
        "validity_inventory": inventory.model_dump(mode="json"),
        "timing": {
            "schema_version": 1,
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": 2_000_000_000,
            "last_earliest_utc_ns": 1_999_999_900,
            "last_latest_utc_ns": 2_000_000_100,
        },
        "frequency_reference": {
            "schema_version": 1,
            "reference": "uncalibrated_prior",
            "center_frequency_hz": None,
            "uncertainty_hz": None,
            "calibration_digest": None,
        },
    }
    return StandardPathInputBindV4.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )


@pytest.mark.parametrize("sample_rate_hz", (2_500_000, 3_000_000, 5_000_000, 10_000_000))
def test_direct_native_tone_observability_agrees_in_physical_units(
    sample_rate_hz: int,
) -> None:
    inventory = _inventory(sample_rate_hz)
    result = run_standard_native_observability(
        _ToneReader(sample_rate_hz, inventory),
        _binding(sample_rate_hz, inventory),
    )

    quality = result.quality.receivers[0]
    mean_energy = quality.energy_sum_ci16_squared / quality.valid_sample_count
    # CI16 quantization is rate-dependent because each rate samples a different
    # set of phases, but the recovered physical energy remains tightly bounded.
    assert mean_energy == pytest.approx(_AMPLITUDE**2, rel=3e-5)
    assert result.power.timeline.timeline[0].mean_power_full_scale_squared == pytest.approx(
        (_AMPLITUDE / 32_768) ** 2,
        rel=3e-5,
    )
    assert result.schedule.accounting.valid_count == result.schedule.accounting.scheduled_count
    assert result.schedule.accounting.gap_excluded_count == 0
    coverage = result.waterfall.waterfall.coverage
    assert coverage.observed_samples == sample_rate_hz
    assert coverage.missing_samples == 0
    assert coverage.transformed_samples == sample_rate_hz // 1024 * 1024

    waterfall = result.waterfall.waterfall

    def waterfall_power(index: tuple[int, int, int]) -> float:
        value = waterfall.tiles[index[0]].receiver_power_dbfs[index[1]][index[2]]
        assert value is not None
        return value

    peak_time_bin, peak_receiver, peak_frequency_bin = max(
        (
            (time_bin, receiver, frequency_bin)
            for time_bin, tile in enumerate(waterfall.tiles)
            for receiver, row in enumerate(tile.receiver_power_dbfs)
            for frequency_bin, value in enumerate(row)
            if value is not None
        ),
        key=waterfall_power,
    )
    del peak_time_bin, peak_receiver
    estimated_hz = waterfall.frequency_bin_centers_hz[peak_frequency_bin]
    assert estimated_hz == pytest.approx(_TONE_HZ, abs=3 * sample_rate_hz / 1024)
