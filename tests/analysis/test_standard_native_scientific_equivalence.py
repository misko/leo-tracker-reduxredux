from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import Decimal

import numpy as np
import pytest

from leo.analysis.standard.configuration import resolve_receiver_standard_sample_rate
from leo.analysis.standard.native_pilot_doppler import (
    build_standard_native_pilot_doppler_segments_v3,
)
from leo.analysis.standard.native_qam import native_qam_sufficient_statistics
from leo.analysis.standard.native_runner import build_standard_native_probe_schedule
from leo.analysis.standard.native_stateful import (
    NativePrimaryProbeOutcome,
    NativeScheduledProbeInput,
    NativeSegmentLocalScience,
    StandardNativeStatefulResult,
    StandardNativeStatefulRunner,
    build_standard_native_stateful_path_v2,
    detect_standard_native_probe_outcome,
)
from leo.analysis.standard.runner import ReceiverStandardConfig
from leo.analysis.starlink.pilot_doppler_segments import (
    build_standard_pilot_doppler_segments_v2,
)
from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)
from leo.analysis.starlink.trajectory_feedback import TrajectoryFeedbackConfig
from leo.contracts.digests import canonical_digest
from leo.contracts.pilot_doppler_segments import StandardPilotDopplerSegmentsV2
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.standard_native_path_report import NativeQamSufficientStatisticsV1
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.validity import ContinuitySegmentV1, ValidityInventoryV1
from leo.domain.iq import IqBlock
from leo.pipeline.validity import DeviceIqSpan, WindowClassification, WindowValidity

_RATES_HZ = (2_500_000, 3_000_000, 5_000_000, 10_000_000)
_CENTER_HZ = 959_687_500
_PILOT_EPOCH_S = 0.0002
_CFO_INTERCEPT_HZ = 40_000.0
_DOPPLER_RATE_HZ_S = 1_200.0
_CARRIER_PHASE_RAD = 0.37
_AMPLITUDE_CI16 = 6_000.0
_PROBE_OFFSETS_MS = tuple(range(0, 1_000, 100))
_STATEFUL_DURATION_S = 2
_SYNTHESIS_BLOCK_SAMPLES = 262_144

# Predeclared physical-unit tolerances. They include native CI16 quantization
# and sample-grid effects, but are much tighter than one Standard CFO bin.
_EPOCH_TOLERANCE_S = 0.5 / min(_RATES_HZ)
_CFO_TOLERANCE_HZ = 35.0
_DOPPLER_RATE_TOLERANCE_HZ_S = 75.0
_TRAJECTORY_CFO_TOLERANCE_HZ = 35.0
_TRAJECTORY_RATE_TOLERANCE_HZ_S = 75.0
_PHASE_TOLERANCE_RAD = 0.08
_QAM_ACCURACY_TOLERANCE = Decimal("0.001")
# Direct 2.5M and 10M grids use 11 versus 44 samples per 4.4 us symbol.
# The same demodulator therefore has a bounded, expected interpolation/quantization
# spread without changing the physical signal or resampling either input.
_QAM_EVM_TOLERANCE = Decimal("0.125")


@dataclass(frozen=True, slots=True)
class _RateScience:
    sample_rate_hz: int
    stateful: StandardNativeStatefulResult
    qam: NativeQamSufficientStatisticsV1


def _native_pilot_ci16(sample_rate_hz: int, sample_count: int) -> np.ndarray:
    """Sample one continuous physical pilot model directly on the requested grid."""

    output = np.empty((sample_count, 1, 2), dtype="<i2")
    pilot_symbols = qin_edge_pilot_symbols(StarlinkEdge.LOWER)
    frequencies_hz = edge_frequencies_hz(StarlinkEdge.LOWER)
    for start in range(0, sample_count, _SYNTHESIS_BLOCK_SAMPLES):
        count = min(_SYNTHESIS_BLOCK_SAMPLES, sample_count - start)
        time_s = (start + np.arange(count, dtype=np.float64)) / sample_rate_hz
        frame_time_s = np.mod(time_s - _PILOT_EPOCH_S, 1.0 / FRAME_RATE_HZ)
        symbol_indexes = np.floor(frame_time_s / OFDM_SYMBOL_DURATION_S).astype(np.int32)
        samples = np.zeros(count, dtype=np.complex128)
        pilot = np.logical_and(symbol_indexes >= 2, symbol_indexes <= 301)
        selected_symbols = symbol_indexes[pilot]
        local_symbol_time_s = frame_time_s[pilot] - selected_symbols * OFDM_SYMBOL_DURATION_S
        pilot_values = np.zeros(len(selected_symbols), dtype=np.complex128)
        for column, frequency_hz in enumerate(frequencies_hz):
            pilot_values += pilot_symbols[selected_symbols - 2, column] * np.exp(
                2j * np.pi * frequency_hz * (local_symbol_time_s - CYCLIC_PREFIX_DURATION_S)
            )
        samples[pilot] = pilot_values / math.sqrt(8.0)
        phase_rad = _CARRIER_PHASE_RAD + 2.0 * np.pi * (
            _CFO_INTERCEPT_HZ * time_s + 0.5 * _DOPPLER_RATE_HZ_S * time_s**2
        )
        samples *= np.exp(1j * phase_rad)
        output[start : start + count, 0, 0] = np.rint(_AMPLITUDE_CI16 * samples.real).astype("<i2")
        output[start : start + count, 0, 1] = np.rint(_AMPLITUDE_CI16 * samples.imag).astype("<i2")
    return output


def _metadata(sample_start: int, sample_count: int) -> IqBlockMetadataV1:
    observed = NanosecondIntervalV1(lower_ns=1, upper_ns=1)
    return IqBlockMetadataV1(
        radio_id="radio-0",
        receiver_ids=(0,),
        sample_count=sample_count,
        session_sample_start=sample_start,
        host_request_utc_ns=observed,
        host_request_monotonic_ns=observed,
    )


class _PilotSegmentReader:
    def __init__(
        self,
        sample_rate_hz: int,
        segment: ContinuitySegmentV1,
        logical_samples: np.ndarray,
    ) -> None:
        self._sample_rate_hz = sample_rate_hz
        self.segment = segment
        self._logical_samples = logical_samples

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
        for local_start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - local_start)
            global_start = self.global_device_sample_start + local_start
            yield IqBlock(
                samples=np.ascontiguousarray(
                    self._logical_samples[global_start : global_start + count]
                ),
                metadata=_metadata(local_start, count),
            )


class _PilotReader:
    center_frequency_hz = _CENTER_HZ
    receiver_ids = (0,)

    def __init__(
        self,
        sample_rate_hz: int,
        inventory: ValidityInventoryV1,
        logical_samples: np.ndarray,
    ) -> None:
        self.sample_rate_hz = sample_rate_hz
        self.sample_count = inventory.logical_sample_count
        self.observed_sample_count = inventory.observed_sample_count
        self.missing_sample_count = inventory.missing_sample_count
        self.validity_inventory = inventory
        self._logical_samples = logical_samples

    def segment_readers(self) -> tuple[_PilotSegmentReader, ...]:
        return tuple(
            _PilotSegmentReader(self.sample_rate_hz, segment, self._logical_samples)
            for segment in self.validity_inventory.segments
            if segment.observed_sample_count
        )

    def classify_window(
        self,
        device_sample_start: int,
        sample_count: int,
    ) -> WindowClassification:
        device_sample_stop = device_sample_start + sample_count
        if device_sample_start < 0 or sample_count <= 0 or device_sample_stop > self.sample_count:
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.OUTSIDE_SPAN,
            )
        missing = sum(
            max(
                0,
                min(device_sample_stop, run.device_sample_stop)
                - max(device_sample_start, run.device_sample_start),
            )
            for run in self.validity_inventory.runs
            if run.content_kind.value == "zero_fill"
        )
        if missing:
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.GAP_OVERLAP,
                missing_sample_count=missing,
            )
        containing = tuple(
            segment.segment_index
            for segment in self.validity_inventory.segments
            if segment.device_sample_start <= device_sample_start
            and device_sample_stop <= segment.device_sample_stop
        )
        if len(containing) == 1:
            return WindowClassification(
                device_sample_start=device_sample_start,
                sample_count=sample_count,
                status=WindowValidity.VALID,
                continuity_segment_index=containing[0],
            )
        crossed = tuple(
            segment.segment_index
            for segment in self.validity_inventory.segments
            if segment.device_sample_start < device_sample_stop
            and device_sample_start < segment.device_sample_stop
        )
        return WindowClassification(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            status=WindowValidity.CONTINUITY_BOUNDARY,
            crossed_segment_indexes=crossed,
        )

    def read_device_span(self, device_sample_start: int, sample_count: int) -> DeviceIqSpan:
        del device_sample_start, sample_count
        raise AssertionError("stateful equivalence must use validity-gated segment readers")

    def iter_masked_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        del block_samples
        raise AssertionError("stateful equivalence must use validity-gated segment readers")
        yield

    def iter_valid_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        del block_samples
        raise AssertionError("stateful equivalence must use validity-gated segment readers")
        yield

    def close(self) -> None:
        pass


def _inventory(
    sample_rate_hz: int,
    sample_count: int,
    *,
    gap: tuple[int, int] | None = None,
) -> ValidityInventoryV1:
    if gap is None:
        runs: tuple[dict[str, object], ...] = (
            {
                "run_index": 0,
                "device_sample_start": 0,
                "sample_count": sample_count,
                "content_kind": "observed",
                "stored_sample_start": 0,
                "continuity_segment_index": 0,
            },
        )
        segments: tuple[dict[str, object], ...] = (
            {
                "segment_index": 0,
                "device_sample_start": 0,
                "device_sample_stop": sample_count,
                "stored_sample_start": 0,
                "stored_sample_stop": sample_count,
            },
        )
        observed = sample_count
        missing = 0
        boundaries = 0
    else:
        gap_start, gap_stop = gap
        gap_count = gap_stop - gap_start
        observed = sample_count - gap_count
        missing = gap_count
        boundaries = 1
        runs = (
            {
                "run_index": 0,
                "device_sample_start": 0,
                "sample_count": gap_start,
                "content_kind": "observed",
                "stored_sample_start": 0,
                "continuity_segment_index": 0,
            },
            {
                "run_index": 1,
                "device_sample_start": gap_start,
                "sample_count": gap_count,
                "content_kind": "zero_fill",
            },
            {
                "run_index": 2,
                "device_sample_start": gap_stop,
                "sample_count": sample_count - gap_stop,
                "content_kind": "observed",
                "stored_sample_start": gap_start,
                "continuity_segment_index": 1,
            },
        )
        segments = (
            {
                "segment_index": 0,
                "device_sample_start": 0,
                "device_sample_stop": gap_start,
                "stored_sample_start": 0,
                "stored_sample_stop": gap_start,
            },
            {
                "segment_index": 1,
                "device_sample_start": gap_stop,
                "device_sample_stop": sample_count,
                "stored_sample_start": gap_start,
                "stored_sample_stop": observed,
                "preceding_missing_sample_count": gap_count,
                "preceding_boundary_reason": "counter_gap",
                "preceding_boundary_header_sha256": canonical_digest(
                    {"rate": sample_rate_hz, "gap": gap}
                ),
            },
        )
    return ValidityInventoryV1.model_validate(
        {
            "stream_id": "stream-0",
            "timeline_sha256": canonical_digest({"timeline": sample_rate_hz, "gap": gap}),
            "gap_map_content_digest": canonical_digest({"gap-map": sample_rate_hz, "gap": gap}),
            "first_device_sample_counter": 100,
            "logical_sample_count": sample_count,
            "observed_sample_count": observed,
            "missing_sample_count": missing,
            "continuity_boundary_count": boundaries,
            "runs": runs,
            "segments": segments,
        }
    )


def _binding(
    sample_rate_hz: int,
    inventory: ValidityInventoryV1,
) -> StandardPathInputBindV4:
    values = {
        "schema_version": 4,
        "algorithm_version": "standard-path-input-bind-v4",
        "session_id": f"native-equivalence-{sample_rate_hz}",
        "stream_id": "stream-0",
        "radio_id": "radio-0",
        "receiver_id": 0,
        "manifest_digest": canonical_digest({"manifest": sample_rate_hz}),
        "raw_integrity_attestation_digest": canonical_digest({"integrity": sample_rate_hz}),
        "selected_stream_digest": canonical_digest({"stream": sample_rate_hz}),
        "compressed_chunk_closure_digest": canonical_digest({"compressed": sample_rate_hz}),
        "uncompressed_chunk_closure_digest": canonical_digest({"uncompressed": sample_rate_hz}),
        "synchronization_inventory_digest": canonical_digest({"sync": sample_rate_hz}),
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
        "declared_sample_count": inventory.logical_sample_count,
        "starlink_channel": 1,
        "starlink_edge": "lower",
        "starlink_tuning_evidence_source": "capture_profile",
        "rf_bandwidth_hz": 2_500_000,
        "requested_sample_count": inventory.logical_sample_count,
        "requested_duration_seconds": str(
            Decimal(inventory.logical_sample_count) / Decimal(sample_rate_hz)
        ),
        "logical_sample_count": inventory.logical_sample_count,
        "observed_sample_count": inventory.observed_sample_count,
        "missing_sample_count": inventory.missing_sample_count,
        "observed_iq_digest": canonical_digest(
            {"observed-iq": sample_rate_hz, "missing": inventory.missing_sample_count}
        ),
        "logical_iq_digest": canonical_digest(
            {"logical-iq": sample_rate_hz, "missing": inventory.missing_sample_count}
        ),
        "timeline_sha256": inventory.timeline_sha256,
        "gap_map_sha256": canonical_digest(
            {"gap-map-file": sample_rate_hz, "missing": inventory.missing_sample_count}
        ),
        "gap_map_content_digest": inventory.gap_map_content_digest,
        "validity_inventory_sha256": inventory.inventory_digest,
        "first_device_sample_counter": 100,
        "last_device_sample_counter_inclusive": 99 + inventory.logical_sample_count,
        "validity_inventory": inventory.model_dump(mode="json"),
        "timing": {
            "schema_version": 1,
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": (
                1_000_000_000 + inventory.logical_sample_count * 1_000_000_000 // sample_rate_hz
            ),
            "last_earliest_utc_ns": (
                999_999_900 + inventory.logical_sample_count * 1_000_000_000 // sample_rate_hz
            ),
            "last_latest_utc_ns": (
                1_000_000_100 + inventory.logical_sample_count * 1_000_000_000 // sample_rate_hz
            ),
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


def _config(sample_rate_hz: int, *, maximum_outer_windows: int = 1) -> ReceiverStandardConfig:
    base = resolve_receiver_standard_sample_rate(
        ReceiverStandardConfig(),
        sample_rate_hz=sample_rate_hz,
    )
    return replace(
        base,
        feedback=replace(
            base.feedback,
            subwindow_ms=1_000,
            probe_offsets_ms=_PROBE_OFFSETS_MS,
            maximum_outer_windows=maximum_outer_windows,
            maximum_scored_candidates_per_probe=1,
            maximum_segmentation_candidates_per_probe=1,
            maximum_workers=1,
        ),
    )


def _run_rate(sample_rate_hz: int) -> _RateScience:
    sample_count = _STATEFUL_DURATION_S * sample_rate_hz
    samples = _native_pilot_ci16(sample_rate_hz, sample_count)
    inventory = _inventory(sample_rate_hz, sample_count)
    binding = _binding(sample_rate_hz, inventory)
    config = _config(sample_rate_hz, maximum_outer_windows=_STATEFUL_DURATION_S)
    stateful = StandardNativeStatefulRunner(config).run(
        _PilotReader(sample_rate_hz, inventory, samples),
        binding,
        edge=StarlinkEdge.LOWER,
    )
    science = stateful.segments[0].local_science
    assert science is not None and science.primary_probe_outcomes
    legacy_v2 = build_standard_pilot_doppler_segments_v2(
        _PilotSegmentReader(sample_rate_hz, inventory.segments[0], samples),
        path_input_binding_digest=science.segment_path_binding_digest,
        pilot_scan_digest=science.pilot_scan_digest,
        detections=science.detections,
        canonical_bank=science.dealiased_trajectory_bank,
        final_bank=science.final_trajectory_bank,
        kalman_tracking=science.kalman_tracking,
        config=config.pilot_doppler_segments,
        edge=StarlinkEdge.LOWER,
    )
    assert legacy_v2 == science.pilot_doppler_segments
    assert legacy_v2.content_digest == science.pilot_doppler_segments.content_digest
    primary_qam_result = science.primary_probe_outcomes[0].primary_qam_result
    assert primary_qam_result is not None
    return _RateScience(
        sample_rate_hz=sample_rate_hz,
        stateful=stateful,
        qam=native_qam_sufficient_statistics(primary_qam_result),
    )


@pytest.fixture(scope="module")
def native_rate_science() -> tuple[_RateScience, ...]:
    return tuple(_run_rate(sample_rate_hz) for sample_rate_hz in _RATES_HZ)


def _local_science(result: _RateScience) -> NativeSegmentLocalScience:
    science = result.stateful.segments[0].local_science
    assert science is not None
    return science


def _wrapped(value: float, period: float) -> float:
    return (value + period / 2.0) % period - period / 2.0


def _physical_cfo_hz(time_s: float) -> float:
    return _CFO_INTERCEPT_HZ + _DOPPLER_RATE_HZ_S * time_s


def _physical_phase_rad(time_s: float) -> float:
    return _CARRIER_PHASE_RAD + 2.0 * math.pi * (
        _CFO_INTERCEPT_HZ * time_s + 0.5 * _DOPPLER_RATE_HZ_S * time_s**2
    )


def test_native_stateful_event_epoch_cfo_and_trajectory_equivalence(
    native_rate_science: tuple[_RateScience, ...],
) -> None:
    expected_event_times_s = tuple(
        outer + offset_ms / 1_000.0
        for outer in range(_STATEFUL_DURATION_S)
        for offset_ms in _PROBE_OFFSETS_MS
    )
    cfo_by_event: list[list[float]] = [[] for _ in expected_event_times_s]
    trajectory_cfo_by_time: dict[float, list[float]] = {time_s: [] for time_s in (0.0, 0.95, 1.9)}

    for result in native_rate_science:
        science = _local_science(result)
        assert result.stateful.analyzed_outer_window_count == _STATEFUL_DURATION_S
        assert tuple(item.time_s for item in science.detections) == pytest.approx(
            expected_event_times_s,
            abs=_EPOCH_TOLERANCE_S,
        )
        assert tuple(
            item.local_epoch_sample / result.sample_rate_hz for item in science.detections
        ) == pytest.approx(
            tuple(_PILOT_EPOCH_S for _ in science.detections),
            abs=_EPOCH_TOLERANCE_S,
        )

        for index, detection in enumerate(science.detections):
            assert detection.acquired_cfo_hz is not None
            physical_epoch_s = detection.time_s + _PILOT_EPOCH_S
            assert detection.acquired_cfo_hz == pytest.approx(
                _physical_cfo_hz(physical_epoch_s),
                abs=_CFO_TOLERANCE_HZ,
            )
            cfo_by_event[index].append(detection.acquired_cfo_hz)

        assert len(science.residual_hough_bank.trajectories) == 1
        raw = science.residual_hough_bank.trajectories[0]
        assert raw.polynomial_degree == 1
        assert raw.point_count == len(expected_event_times_s)
        assert raw.coefficients_hz[0] == pytest.approx(
            _DOPPLER_RATE_HZ_S,
            abs=_TRAJECTORY_RATE_TOLERANCE_HZ_S,
        )
        assert raw.coefficients_hz[1] == pytest.approx(
            _CFO_INTERCEPT_HZ,
            abs=_TRAJECTORY_CFO_TOLERANCE_HZ,
        )
        assert science.cfo_alias_map.status == "complete"
        assert science.dealiased_trajectory_bank.status == "complete"
        assert science.cfo_lift_replay.returned_lift_count == 1
        assert science.final_trajectory_bank.status == "complete"
        assert science.final_trajectory_bank.returned_trajectory_count == 1
        final = science.final_trajectory_bank.trajectories[0]
        assert final.polynomial_degree == 1
        assert final.absolute_coefficients_hz[0] == pytest.approx(
            _DOPPLER_RATE_HZ_S,
            abs=_TRAJECTORY_RATE_TOLERANCE_HZ_S,
        )
        for time_s, values in trajectory_cfo_by_time.items():
            fitted = float(
                np.polyval(
                    final.absolute_coefficients_hz,
                    time_s - final.reference_time_s,
                )
            )
            assert fitted == pytest.approx(
                _physical_cfo_hz(time_s),
                abs=_TRAJECTORY_CFO_TOLERANCE_HZ,
            )
            values.append(fitted)

    for values in cfo_by_event:
        assert max(values) - min(values) <= _CFO_TOLERANCE_HZ
    for values in trajectory_cfo_by_time.values():
        assert max(values) - min(values) <= _TRAJECTORY_CFO_TOLERANCE_HZ


def test_native_stateful_phase_doppler_and_qam_statistics_are_equivalent(
    native_rate_science: tuple[_RateScience, ...],
) -> None:
    qam_accuracies: list[Decimal] = []
    qam_evm: list[Decimal] = []

    for result in native_rate_science:
        science = _local_science(result)
        assert science.kalman_tracking.status == "complete"
        assert science.kalman_tracking.returned_track_count == 1
        track = science.kalman_tracking.tracks[0]
        assert track.status == "complete"
        assert track.frames
        for frame in track.frames:
            expected_phase = _physical_phase_rad(frame.time_s)
            assert abs(_wrapped(frame.measurement_phase_rad - expected_phase, math.pi)) <= (
                _PHASE_TOLERANCE_RAD
            )
            assert abs(_wrapped(frame.carrier_phase_rad - expected_phase, math.pi)) <= (
                _PHASE_TOLERANCE_RAD
            )
            assert frame.doppler_shift_hz == pytest.approx(
                _physical_cfo_hz(frame.time_s),
                abs=_CFO_TOLERANCE_HZ,
            )

        doppler = science.pilot_doppler_segments
        assert doppler.status == "complete"
        assert doppler.segments
        assert doppler.qualified_segment_count == doppler.analyzed_segment_count
        for segment in doppler.segments:
            assert segment.qualified
            assert segment.local_doppler_rate_hz_s == pytest.approx(
                _DOPPLER_RATE_HZ_S,
                abs=_DOPPLER_RATE_TOLERANCE_HZ_S,
            )
            assert segment.local_cfo_at_reference_hz == pytest.approx(
                _physical_cfo_hz(segment.reference_time_s),
                abs=_CFO_TOLERANCE_HZ,
            )
            assert segment.phase_innovation_rms_rad is not None
            assert segment.phase_innovation_rms_rad <= _PHASE_TOLERANCE_RAD

        first_detection = science.detections[0]
        assert science.primary_probe_outcomes[0].detection == first_detection
        assert result.qam.qam_result_count == 1
        assert result.qam.frame_count == 14
        assert result.qam.symbol_count == 2_400
        assert result.qam.correct_symbol_count == result.qam.symbol_count
        assert result.qam.hard_symbol_accuracy is not None
        assert result.qam.rms_evm is not None
        assert not result.qam.invalid_device_axis_samples_included
        assert float(result.qam.rms_evm) == pytest.approx(
            math.sqrt(float(result.qam.squared_error_sum / result.qam.reference_energy_sum)),
            rel=1e-12,
        )
        assert first_detection.qam_accuracy == pytest.approx(
            float(result.qam.hard_symbol_accuracy),
            abs=1e-15,
        )
        assert first_detection.qam_evm == pytest.approx(
            float(result.qam.rms_evm),
            rel=1e-6,
        )
        qam_accuracies.append(result.qam.hard_symbol_accuracy)
        qam_evm.append(result.qam.rms_evm)

    assert max(qam_accuracies) - min(qam_accuracies) <= _QAM_ACCURACY_TOLERANCE
    assert max(qam_evm) - min(qam_evm) <= _QAM_EVM_TOLERANCE


def test_nonempty_multirate_v3_phase_evidence_closes_global_multiwindow_geometry(
    native_rate_science: tuple[_RateScience, ...],
) -> None:
    for result in native_rate_science:
        sample_count = _STATEFUL_DURATION_S * result.sample_rate_hz
        inventory = _inventory(result.sample_rate_hz, sample_count)
        binding = _binding(result.sample_rate_hz, inventory)
        config = _config(
            result.sample_rate_hz,
            maximum_outer_windows=_STATEFUL_DURATION_S,
        )
        stateful_path = build_standard_native_stateful_path_v2(
            result.stateful,
            binding,
            config,
            edge=StarlinkEdge.LOWER,
        )
        stateful_document = stateful_path.model_dump(mode="json")
        v3 = build_standard_native_pilot_doppler_segments_v3(
            result.stateful,
            binding,
            stateful_path,
            stateful_path_product_digest=canonical_digest(stateful_document),
            config=config,
            edge=StarlinkEdge.LOWER,
        )

        assert v3.segments
        assert v3.source_v2_locklet_count == len(
            _local_science(result).pilot_doppler_segments.segments
        )
        assert any(item.global_source_probe_sample_start > 0 for item in v3.segments)
        for segment in v3.segments:
            assert segment.carrier_phase_period_rad == math.pi
            assert segment.supported_frame_count == len(segment.supported_frame_indexes)
            assert all(
                segment.global_start_time_s * result.sample_rate_hz
                <= interval.previous_global_reference_device_sample
                < interval.global_reference_device_sample
                <= segment.global_end_time_s * result.sample_rate_hz + 1e-3
                for interval in segment.intervals
            )


def test_v3_marks_nested_v2_track_truncation_partial_even_when_stateful_is_complete(
    native_rate_science: tuple[_RateScience, ...],
) -> None:
    result = native_rate_science[0]
    science = _local_science(result)
    legacy_document = science.pilot_doppler_segments.model_dump(mode="json")
    legacy_document["source_track_count"] += 1
    legacy_document["truncated_track_count"] += 1
    legacy_body = {key: value for key, value in legacy_document.items() if key != "content_digest"}
    truncated_legacy = StandardPilotDopplerSegmentsV2.model_validate(
        {**legacy_body, "content_digest": canonical_digest(legacy_body)}
    )
    mutated_science = replace(science, pilot_doppler_segments=truncated_legacy)
    mutated_segment = replace(result.stateful.segments[0], local_science=mutated_science)
    mutated_result = replace(result.stateful, segments=(mutated_segment,))
    sample_count = _STATEFUL_DURATION_S * result.sample_rate_hz
    inventory = _inventory(result.sample_rate_hz, sample_count)
    binding = _binding(result.sample_rate_hz, inventory)
    config = _config(
        result.sample_rate_hz,
        maximum_outer_windows=_STATEFUL_DURATION_S,
    )
    stateful_path = build_standard_native_stateful_path_v2(
        mutated_result,
        binding,
        config,
        edge=StarlinkEdge.LOWER,
    )
    stateful_document = stateful_path.model_dump(mode="json")
    v3 = build_standard_native_pilot_doppler_segments_v3(
        mutated_result,
        binding,
        stateful_path,
        stateful_path_product_digest=canonical_digest(stateful_document),
        config=config,
        edge=StarlinkEdge.LOWER,
    )

    assert stateful_path.stateful_science_status == "complete"
    assert truncated_legacy.status == "complete"
    assert v3.bounded_local_track_truncation_present
    assert v3.status == "partial"
    assert "track truncation" in v3.reason


@pytest.mark.parametrize("sample_rate_hz", _RATES_HZ)
def test_gapped_native_stateful_execution_never_bridges_continuity_segments(
    sample_rate_hz: int,
) -> None:
    sample_count = sample_rate_hz
    gap = (sample_rate_hz * 495 // 1_000, sample_rate_hz * 525 // 1_000)
    samples = _native_pilot_ci16(sample_rate_hz, sample_count)
    samples[gap[0] : gap[1]] = 0
    inventory = _inventory(sample_rate_hz, sample_count, gap=gap)
    binding = _binding(sample_rate_hz, inventory)
    config = _config(sample_rate_hz, maximum_outer_windows=2)
    reader = _PilotReader(sample_rate_hz, inventory, samples)
    schedule = build_standard_native_probe_schedule(
        reader,
        binding,
        subwindow_ms=config.feedback.subwindow_ms,
        probe_ms=config.feedback.probe_ms,
        probe_offsets_ms=config.feedback.probe_offsets_ms,
        maximum_coarse_windows=config.feedback.maximum_outer_windows,
    )
    computed_support: list[tuple[int, int, int]] = []

    def recording_detector(
        item: NativeScheduledProbeInput,
        feedback: TrajectoryFeedbackConfig,
        edge: StarlinkEdge,
    ) -> NativePrimaryProbeOutcome:
        computed_support.append(
            (
                item.continuity_segment_index,
                item.global_device_sample_start,
                item.global_device_sample_stop,
            )
        )
        return detect_standard_native_probe_outcome(item, feedback, edge)

    result = StandardNativeStatefulRunner(
        config,
        probe_outcome_detector=recording_detector,
    ).run_global_probe_schedule(
        reader,
        binding,
        schedule,
        edge=StarlinkEdge.LOWER,
        capture_qam=True,
    )

    assert schedule.accounting.scheduled_count == len(_PROBE_OFFSETS_MS)
    assert schedule.accounting.valid_count == len(_PROBE_OFFSETS_MS) - 1
    assert schedule.accounting.gap_excluded_count == 1
    assert len(computed_support) == schedule.accounting.valid_count
    assert len(result.qam_probe_evidence) == schedule.accounting.valid_count
    assert all(
        not item.statistics.invalid_device_axis_samples_included
        for item in result.qam_probe_evidence
    )
    segments = {item.segment_index: item for item in inventory.segments}
    for segment_index, start, stop in computed_support:
        segment = segments[segment_index]
        assert segment.device_sample_start <= start < stop <= segment.device_sample_stop
        assert stop <= gap[0] or start >= gap[1]

    assert tuple(item.disposition.value for item in result.segments) == (
        "analyzed",
        "analyzed",
    )
    assert tuple(
        len(item.local_science.detections) if item.local_science is not None else 0
        for item in result.segments
    ) == (5, 4)
    for segment_result in result.segments:
        science = segment_result.local_science
        assert science is not None
        assert science.residual_hough_bank.observation_count == len(science.detections)
        # The combined nine points satisfy the production Hough support/span
        # gates; the reset-local 5/4 partitions deliberately do not. A fit here
        # would therefore be direct evidence that state crossed the gap.
        assert science.residual_hough_bank.trajectories == ()
        assert science.final_trajectory_bank.status == "no_result"
        assert science.kalman_tracking.status == "no_result"
        assert science.pilot_doppler_segments.status == "no_result"
        for detection in science.detections:
            global_start = segment_result.device_sample_start + detection.sample_start
            assert (
                segment_result.device_sample_start
                <= global_start
                < segment_result.device_sample_stop
            )
            assert global_start + sample_rate_hz * config.feedback.probe_ms // 1_000 <= (
                segment_result.device_sample_stop
            )
