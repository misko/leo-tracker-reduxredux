from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    detect_pilot_method_candidates,
)
from leo.analysis.starlink.pilot_search_geometry import (
    PilotSearchGeometryError,
    compile_pilot_search_geometry,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame
from leo.contracts.states import StarlinkEdge


@pytest.mark.parametrize(
    (
        "edge",
        "sample_rate_hz",
        "rf_bandwidth_hz",
        "tuned_center_frequency_hz",
        "expected_pilot_baseband_hz",
    ),
    (
        (StarlinkEdge.LOWER, 2_500_000, 2_500_000, 959_687_500, 0.0),
        (StarlinkEdge.UPPER, 2_500_000, 2_500_000, 1_190_312_500, 0.0),
        (StarlinkEdge.LOWER, 5_000_000, 5_000_000, 959_687_500, 0.0),
        (StarlinkEdge.UPPER, 5_000_000, 5_000_000, 1_190_312_500, 0.0),
        (StarlinkEdge.LOWER, 10_000_000, 10_000_000, 960_000_000, -312_500.0),
        (StarlinkEdge.UPPER, 10_000_000, 10_000_000, 1_190_000_000, 312_500.0),
        (StarlinkEdge.LOWER, 15_000_000, 15_000_000, 962_500_000, -2_812_500.0),
        (StarlinkEdge.UPPER, 15_000_000, 15_000_000, 1_187_500_000, 2_812_500.0),
    ),
)
def test_search_is_centered_on_the_bound_pilot_at_every_native_geometry(
    edge: StarlinkEdge,
    sample_rate_hz: int,
    rf_bandwidth_hz: int,
    tuned_center_frequency_hz: int,
    expected_pilot_baseband_hz: float,
) -> None:
    geometry = compile_pilot_search_geometry(
        receiver_id="rx0",
        starlink_channel=1,
        edge=edge,
        tuned_center_frequency_hz=tuned_center_frequency_hz,
        sample_rate_hz=sample_rate_hz,
        rf_bandwidth_hz=rf_bandwidth_hz,
        residual_cfo_min_hz=-400_000.0,
        residual_cfo_max_hz=400_000.0,
    )

    assert geometry.nominal_pilot_baseband_hz == expected_pilot_baseband_hz
    assert geometry.search_baseband_min_hz == expected_pilot_baseband_hz - 400_000.0
    assert geometry.search_baseband_max_hz == expected_pilot_baseband_hz + 400_000.0
    assert geometry.frequency_reference.center_hz == expected_pilot_baseband_hz


def test_search_requires_the_complete_qin_band_and_residual_budget_to_be_observable() -> None:
    with pytest.raises(PilotSearchGeometryError, match="complete pilot search band"):
        compile_pilot_search_geometry(
            receiver_id="rx0",
            starlink_channel=1,
            edge=StarlinkEdge.UPPER,
            tuned_center_frequency_hz=1_190_000_000,
            sample_rate_hz=2_500_000,
            rf_bandwidth_hz=2_500_000,
            residual_cfo_min_hz=-400_000.0,
            residual_cfo_max_hz=400_000.0,
        )


def test_frequency_reference_digest_binds_the_complete_search_geometry() -> None:
    first = compile_pilot_search_geometry(
        receiver_id="rx0",
        starlink_channel=1,
        edge=StarlinkEdge.UPPER,
        tuned_center_frequency_hz=1_190_000_000,
        sample_rate_hz=10_000_000,
        rf_bandwidth_hz=10_000_000,
        residual_cfo_min_hz=-400_000.0,
        residual_cfo_max_hz=400_000.0,
    )
    second = compile_pilot_search_geometry(
        receiver_id="rx0",
        starlink_channel=1,
        edge=StarlinkEdge.UPPER,
        tuned_center_frequency_hz=1_190_100_000,
        sample_rate_hz=10_000_000,
        rf_bandwidth_hz=10_000_000,
        residual_cfo_min_hz=-400_000.0,
        residual_cfo_max_hz=400_000.0,
    )

    assert first.frequency_reference.calibration_sha256 != (
        second.frequency_reference.calibration_sha256
    )


def test_native_10ms_glrt_recovers_a_pilot_outside_the_old_dc_centered_search() -> None:
    sample_rate_hz = 10_000_000
    sample_count = 50_000
    epoch_sample = 37
    actual_pilot_baseband_hz = 650_000.0
    samples = np.zeros(sample_count, dtype=np.complex128)
    template = qin_edge_pilot_frame(sample_rate_hz, StarlinkEdge.UPPER)
    frame_index = 0
    while True:
        frame_start = epoch_sample + round(frame_index * sample_rate_hz / FRAME_RATE_HZ)
        if frame_start + template.size > sample_count:
            break
        indexes = np.arange(frame_start, frame_start + template.size)
        samples[frame_start : frame_start + template.size] += template * np.exp(
            2j * np.pi * actual_pilot_baseband_hz * indexes / sample_rate_hz
        )
        frame_index += 1

    acquisition = SymbolwiseAcquisitionConfig(maximum_probe_samples=sample_count)
    geometry = compile_pilot_search_geometry(
        receiver_id="rx0",
        starlink_channel=1,
        edge=StarlinkEdge.UPPER,
        tuned_center_frequency_hz=1_190_000_000,
        sample_rate_hz=sample_rate_hz,
        rf_bandwidth_hz=sample_rate_hz,
        residual_cfo_min_hz=acquisition.residual_cfo_min_hz,
        residual_cfo_max_hz=acquisition.residual_cfo_max_hz,
    )

    corrected = detect_pilot_method_candidates(
        samples,
        sample_rate_hz,
        sample_start=0,
        calibration=geometry.frequency_reference,
        acquisition_config=acquisition,
        maximum_scored_candidates=1,
        edge=StarlinkEdge.UPPER,
    )
    old_dc_centered = detect_pilot_method_candidates(
        samples,
        sample_rate_hz,
        sample_start=0,
        calibration=ReceiverFrequencyCalibration("rx0", 0.0, "1" * 64),
        acquisition_config=acquisition,
        maximum_scored_candidates=1,
        edge=StarlinkEdge.UPPER,
    )
    corrected_glrt = next(score for score in corrected.scores if score.method is PilotMethod.GLRT64)
    old_glrt = next(score for score in old_dc_centered.scores if score.method is PilotMethod.GLRT64)

    assert corrected.acquired_cfo_hz == pytest.approx(actual_pilot_baseband_hz)
    assert corrected_glrt.margin > 0.8
    assert old_glrt.margin < 0.1
