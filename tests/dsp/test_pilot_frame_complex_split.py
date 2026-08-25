from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from leo.analysis.qam import (
    PilotFrameComplexFold,
    PilotFrameComplexSplitObservation,
    estimate_edge_pilot_frame_complex_split,
)
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, StarlinkEdge

RATE = 2_500_000.0
FRAME_CONTENT = round(302 * RATE * OFDM_SYMBOL_DURATION_S)


def _guarded_frame(
    *,
    frame_start_sample: int,
    absolute_cfo_hz: float,
    phase_rad: float = 0.0,
    edge: StarlinkEdge = StarlinkEdge.LOWER,
) -> np.ndarray:
    template = np.asarray(qin_edge_pilot_frame(RATE, edge), dtype=np.complex128)
    samples = np.zeros(FRAME_CONTENT + 2, dtype=np.complex128)
    local_samples = np.arange(FRAME_CONTENT)
    absolute_samples = frame_start_sample + local_samples
    samples[1:-1] = template[:FRAME_CONTENT] * np.exp(
        1j * (2.0 * np.pi * absolute_cfo_hz * absolute_samples / RATE + phase_rad)
    )
    return samples


def _estimate(
    samples: np.ndarray,
    *,
    frame_start_sample: int,
    acquisition_absolute_cfo_hz: float,
) -> PilotFrameComplexSplitObservation:
    return estimate_edge_pilot_frame_complex_split(
        samples,
        RATE,
        frame_start_sample=frame_start_sample,
        acquisition_absolute_cfo_hz=acquisition_absolute_cfo_hz,
        edge=StarlinkEdge.LOWER,
    )


def test_complex_split_recovers_synthetic_cfo_and_exposes_both_folds() -> None:
    frame_start = 1_234_567
    acquisition_cfo_hz = 200_000.0
    residual_cfo_hz = 317.4
    samples = _guarded_frame(
        frame_start_sample=frame_start,
        absolute_cfo_hz=acquisition_cfo_hz + residual_cfo_hz,
    )

    result = _estimate(
        samples,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=acquisition_cfo_hz,
    )

    assert isinstance(result, PilotFrameComplexSplitObservation)
    assert result.status is NumericalStatus.COMPLETE
    assert result.training_supported
    assert result.training_rejection_reasons == ()
    assert result.frame_start_sample == frame_start
    assert result.reference_sample > frame_start
    assert result.known_symbols_only and result.candidate_only
    assert result.carrier_phase_period_rad == math.pi
    assert not result.absolute_carrier_phase_resolved
    assert result.frame_timing_is_receiver_relative
    assert isinstance(result.even, PilotFrameComplexFold)
    assert isinstance(result.odd, PilotFrameComplexFold)

    for fold in (result.even, result.odd):
        assert fold.residual_cfo_hz == pytest.approx(residual_cfo_hz, abs=0.5)
        assert fold.absolute_cfo_hz == pytest.approx(
            acquisition_cfo_hz + residual_cfo_hz,
            abs=0.5,
        )
        assert math.isfinite(fold.frequency_uncertainty_hz)
        assert fold.frequency_uncertainty_hz >= 0.0
        assert fold.exact_coherence > 0.95
        assert fold.control_coherence < 0.1
        assert fold.coherence_margin > 0.94
        assert fold.phase_residual_rms_rad < 0.05
        assert not fold.search_boundary
        assert fold.channel_vector.shape == (8,)
        assert np.issubdtype(fold.channel_vector.dtype, np.complexfloating)


def test_complex_channel_gauge_is_independent_of_acquisition_seed() -> None:
    frame_start = 1_234_567
    absolute_cfo_hz = 200_317.4
    samples = _guarded_frame(
        frame_start_sample=frame_start,
        absolute_cfo_hz=absolute_cfo_hz,
        phase_rad=0.37,
    )

    baseline = _estimate(
        samples,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=200_000.0,
    )
    shifted_seed = _estimate(
        samples,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=199_250.0,
    )

    assert baseline.even is not None and baseline.odd is not None
    assert shifted_seed.even is not None and shifted_seed.odd is not None
    expected_channel = np.exp(
        1j * (2.0 * np.pi * absolute_cfo_hz * baseline.reference_sample / RATE + 0.37)
    )
    for original, shifted in (
        (baseline.even, shifted_seed.even),
        (baseline.odd, shifted_seed.odd),
    ):
        assert shifted.absolute_cfo_hz == pytest.approx(original.absolute_cfo_hz, abs=0.5)
        np.testing.assert_allclose(
            original.channel_vector,
            np.full(8, expected_channel),
            rtol=5e-2,
            atol=2e-2,
        )
        np.testing.assert_allclose(
            shifted.channel_vector,
            original.channel_vector,
            rtol=2e-3,
            atol=2e-3,
        )


def test_pi_phase_offset_flips_channel_sign_without_changing_cfo() -> None:
    frame_start = 81_337
    acquisition_cfo_hz = -125_000.0
    residual_cfo_hz = -421.25
    baseline_samples = _guarded_frame(
        frame_start_sample=frame_start,
        absolute_cfo_hz=acquisition_cfo_hz + residual_cfo_hz,
        phase_rad=0.23,
    )
    inverted_samples = -baseline_samples

    baseline = _estimate(
        baseline_samples,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=acquisition_cfo_hz,
    )
    inverted = _estimate(
        inverted_samples,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=acquisition_cfo_hz,
    )

    assert baseline.training_supported == inverted.training_supported is True
    assert baseline.even is not None and baseline.odd is not None
    assert inverted.even is not None and inverted.odd is not None
    for original, shifted in ((baseline.even, inverted.even), (baseline.odd, inverted.odd)):
        assert shifted.residual_cfo_hz == pytest.approx(original.residual_cfo_hz, abs=1e-6)
        assert shifted.absolute_cfo_hz == pytest.approx(original.absolute_cfo_hz, abs=1e-6)
        assert shifted.frequency_uncertainty_hz == pytest.approx(
            original.frequency_uncertainty_hz,
            abs=1e-9,
        )
        np.testing.assert_allclose(shifted.channel_vector, -original.channel_vector, atol=1e-9)


def test_odd_corruption_cannot_change_membership_or_even_fold() -> None:
    frame_start = 91_001
    acquisition_cfo_hz = 80_000.0
    residual_cfo_hz = 240.0
    clean_samples = _guarded_frame(
        frame_start_sample=frame_start,
        absolute_cfo_hz=acquisition_cfo_hz + residual_cfo_hz,
    )
    corrupted_samples = clean_samples.copy()
    reference_offset = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S) * RATE
    )
    for pilot_row in range(1, 300, 2):
        symbol = pilot_row + 2
        start = round(symbol * RATE * OFDM_SYMBOL_DURATION_S)
        stop = round((symbol + 1) * RATE * OFDM_SYMBOL_DURATION_S)
        local = np.arange(start, stop, dtype=float)
        corrupted_samples[1 + start : 1 + stop] *= np.exp(
            2j * np.pi * 2_000.0 * (local - reference_offset) / RATE
        )

    clean = _estimate(
        clean_samples,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=acquisition_cfo_hz,
    )
    corrupted = _estimate(
        corrupted_samples,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=acquisition_cfo_hz,
    )

    assert clean.training_supported == corrupted.training_supported is True
    assert clean.training_rejection_reasons == corrupted.training_rejection_reasons == ()
    assert clean.even is not None and clean.odd is not None
    assert corrupted.even is not None and corrupted.odd is not None
    for field_name in (
        "residual_cfo_hz",
        "absolute_cfo_hz",
        "frequency_uncertainty_hz",
        "exact_coherence",
        "control_coherence",
        "coherence_margin",
        "phase_residual_rms_rad",
        "search_boundary",
    ):
        assert getattr(corrupted.even, field_name) == getattr(clean.even, field_name)
    np.testing.assert_array_equal(corrupted.even.channel_vector, clean.even.channel_vector)
    assert clean.odd.residual_cfo_hz == pytest.approx(residual_cfo_hz, abs=0.5)
    assert corrupted.odd.search_boundary
    assert corrupted.odd.residual_cfo_hz == pytest.approx(2_000.0, abs=0.1)


def test_complex_split_returns_typed_no_result_for_zero_energy() -> None:
    result = _estimate(
        np.zeros(FRAME_CONTENT + 2, dtype=np.complex128),
        frame_start_sample=1,
        acquisition_absolute_cfo_hz=0.0,
    )

    assert isinstance(result, PilotFrameComplexSplitObservation)
    assert result.status is NumericalStatus.NO_RESULT
    assert not result.training_supported
    assert result.training_rejection_reasons == ("zero_pilot_energy",)
    assert result.even is None
    assert result.odd is None
    assert result.frame_start_sample == 1
    assert result.reference_sample > 1
    assert result.known_symbols_only and result.candidate_only
    assert result.carrier_phase_period_rad == math.pi
    assert not result.absolute_carrier_phase_resolved
    assert result.frame_timing_is_receiver_relative


@pytest.mark.parametrize("guard_index", (0, -1))
def test_guard_energy_cannot_masquerade_as_pilot_energy(guard_index: int) -> None:
    samples = np.zeros(FRAME_CONTENT + 2, dtype=np.complex128)
    samples[guard_index] = 1.0 + 0.5j

    result = _estimate(
        samples,
        frame_start_sample=1,
        acquisition_absolute_cfo_hz=0.0,
    )

    assert result.status is NumericalStatus.NO_RESULT
    assert not result.training_supported
    assert result.training_rejection_reasons == ("zero_pilot_energy",)
    assert result.even is None and result.odd is None


def test_complex_fold_and_channel_vector_are_immutable() -> None:
    result = _estimate(
        _guarded_frame(frame_start_sample=1, absolute_cfo_hz=120.0),
        frame_start_sample=1,
        acquisition_absolute_cfo_hz=0.0,
    )

    assert result.even is not None and result.odd is not None
    with pytest.raises(FrozenInstanceError):
        result.training_supported = False  # type: ignore[misc]
    for fold in (result.even, result.odd):
        assert not fold.channel_vector.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            fold.channel_vector[0] = 0.0
        with pytest.raises(FrozenInstanceError):
            fold.residual_cfo_hz = 0.0  # type: ignore[misc]


def test_complex_split_rejects_malformed_guarded_frames_and_coordinates() -> None:
    valid = np.zeros(FRAME_CONTENT + 2, dtype=np.complex128)
    arguments = {
        "frame_start_sample": 1,
        "acquisition_absolute_cfo_hz": 0.0,
        "edge": StarlinkEdge.LOWER,
    }

    with pytest.raises(ValueError, match="one dimensional"):
        estimate_edge_pilot_frame_complex_split(valid[:, None], RATE, **arguments)
    with pytest.raises(ValueError, match="finite"):
        nonfinite = valid.copy()
        nonfinite[10] = np.nan
        estimate_edge_pilot_frame_complex_split(nonfinite, RATE, **arguments)
    with pytest.raises(ValueError, match="at least"):
        estimate_edge_pilot_frame_complex_split(valid, 1_000_000.0, **arguments)
    with pytest.raises(ValueError, match="integer sample"):
        estimate_edge_pilot_frame_complex_split(
            valid,
            RATE,
            **{**arguments, "frame_start_sample": 1.5},
        )
    with pytest.raises(ValueError, match="preceding recording sample"):
        estimate_edge_pilot_frame_complex_split(
            valid,
            RATE,
            **{**arguments, "frame_start_sample": 0},
        )
    with pytest.raises(ValueError, match="CFO must be finite"):
        estimate_edge_pilot_frame_complex_split(
            valid,
            RATE,
            **{**arguments, "acquisition_absolute_cfo_hz": math.inf},
        )
    with pytest.raises(ValueError, match="one-sample guards"):
        estimate_edge_pilot_frame_complex_split(valid[:-1], RATE, **arguments)
