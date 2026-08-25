from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.qam import (
    PilotFrameCfoConfig,
    evaluate_edge_pilot_frame_cfo_likelihood,
)
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, StarlinkEdge

RATE = 2_500_000.0
FRAME_START = 1_234_567
ACQUISITION_CFO_HZ = 200_000.0


def _raw_frame(*, residual_cfo_hz: float) -> np.ndarray:
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)
    template = np.asarray(qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER), np.complex128)
    samples = np.zeros(frame_content + 2, dtype=np.complex128)
    indexes = np.arange(frame_content)
    samples[1 + indexes] = template[:frame_content] * np.exp(
        2j * np.pi * (ACQUISITION_CFO_HZ + residual_cfo_hz) * (FRAME_START + indexes) / RATE
    )
    return samples


def test_frame_likelihood_profile_recovers_both_parity_folds_and_pairs_controls() -> None:
    injected_hz = 317.4
    grid = np.arange(-1_000.0, 1_000.1, 10.0)

    result = evaluate_edge_pilot_frame_cfo_likelihood(
        _raw_frame(residual_cfo_hz=injected_hz),
        RATE,
        frame_start_sample=FRAME_START,
        acquisition_absolute_cfo_hz=ACQUISITION_CFO_HZ,
        edge=StarlinkEdge.LOWER,
        residual_grid_hz=grid,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.split_validation.training_supported
    assert result.split_validation.even_residual_cfo_hz == pytest.approx(injected_hz, abs=0.5)
    assert result.split_validation.odd_residual_cfo_hz == pytest.approx(injected_hz, abs=0.5)
    assert result.odd_symbols_influenced_fit is False
    assert result.known_symbols_only and result.candidate_only

    curves = (
        result.even_exact_log_likelihood,
        result.even_control_log_likelihood,
        result.odd_exact_log_likelihood,
        result.odd_control_log_likelihood,
    )
    assert all(curve.shape == grid.shape for curve in curves)
    assert all(not curve.flags.writeable for curve in (result.residual_grid_hz, *curves))
    assert grid[int(np.argmax(result.even_exact_log_likelihood))] == pytest.approx(
        injected_hz, abs=5.0
    )
    assert grid[int(np.argmax(result.odd_exact_log_likelihood))] == pytest.approx(
        injected_hz, abs=5.0
    )
    assert np.max(result.even_exact_log_likelihood) == pytest.approx(0.0, abs=1e-12)
    assert np.max(result.odd_exact_log_likelihood) == pytest.approx(0.0, abs=1e-12)
    assert np.max(result.even_control_log_likelihood) < -100.0
    assert np.max(result.odd_control_log_likelihood) < -100.0

    frozen_grid = result.residual_grid_hz.copy()
    grid[0] = -999_999.0
    assert np.array_equal(result.residual_grid_hz, frozen_grid)


@pytest.mark.parametrize(
    ("grid", "message"),
    (
        (np.asarray([-1.0, 1.0]), "at least three"),
        (np.asarray([-1.0, 0.0, 0.0, 1.0]), "strictly increasing"),
        (np.asarray([-1.0, 0.0, np.nan]), "finite"),
        (np.asarray([-2_001.0, 0.0, 1.0]), "acquisition basin"),
    ),
)
def test_frame_likelihood_profile_rejects_invalid_frequency_grids(
    grid: np.ndarray,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        evaluate_edge_pilot_frame_cfo_likelihood(
            _raw_frame(residual_cfo_hz=100.0),
            RATE,
            frame_start_sample=FRAME_START,
            acquisition_absolute_cfo_hz=ACQUISITION_CFO_HZ,
            edge=StarlinkEdge.LOWER,
            residual_grid_hz=grid,
            config=PilotFrameCfoConfig(),
        )


def test_zero_energy_frame_returns_a_typed_empty_profile() -> None:
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)
    grid = np.asarray([-100.0, 0.0, 100.0])

    result = evaluate_edge_pilot_frame_cfo_likelihood(
        np.zeros(frame_content + 2, dtype=np.complex128),
        RATE,
        frame_start_sample=FRAME_START,
        acquisition_absolute_cfo_hz=ACQUISITION_CFO_HZ,
        edge=StarlinkEdge.LOWER,
        residual_grid_hz=grid,
    )

    assert result.status is NumericalStatus.NO_RESULT
    assert result.split_validation.status is NumericalStatus.NO_RESULT
    assert not result.split_validation.training_supported
    assert np.array_equal(result.residual_grid_hz, grid)
    assert result.even_exact_log_likelihood.size == 0
    assert result.even_control_log_likelihood.size == 0
    assert result.odd_exact_log_likelihood.size == 0
    assert result.odd_control_log_likelihood.size == 0
