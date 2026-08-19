from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink.acquisition import (
    DEFAULT_ACQUIRE_SYMBOLS,
    DEFAULT_ANCHOR_SYMBOLS,
    _conditioned_frame_scores,
    _folded_anchor_score_grid,
    _folded_anchor_scores,
    _normalized_frame_scores,
    conditioned_frame_score,
    normalized_frame_score,
)
from leo.analysis.starlink.pilot_methods import (
    _conditioned_correlation_workspace,
    _glrt,
    _glrt_pair,
    _symbol_correlations,
)
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    qin_edge_pilot_frame,
)

_RATE = 2_500_000


@pytest.fixture(scope="module")
def probe() -> np.ndarray:
    generator = np.random.default_rng(0x5A17)
    return generator.normal(size=50_000) + 1j * generator.normal(size=50_000)


def test_vector_cfo_grids_match_scalar_scientific_kernels(probe: np.ndarray) -> None:
    template = np.asarray(qin_edge_pilot_frame(_RATE, "lower"), np.complex128)
    cfo_grid = (-1_500.0, -1_000.0, -500.0, 0.0, 500.0)

    expected_normalized = tuple(
        normalized_frame_score(
            probe, template, _RATE, 347, cfo, DEFAULT_ACQUIRE_SYMBOLS
        )[0]
        for cfo in cfo_grid
    )
    expected_conditioned = tuple(
        conditioned_frame_score(probe, template, _RATE, 347, cfo)[0]
        for cfo in cfo_grid
    )

    np.testing.assert_allclose(
        _normalized_frame_scores(
            probe, template, _RATE, 347, cfo_grid, DEFAULT_ACQUIRE_SYMBOLS
        ),
        expected_normalized,
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        _conditioned_frame_scores(probe, template, _RATE, 347, cfo_grid),
        expected_conditioned,
        rtol=1e-12,
        atol=1e-12,
    )


def test_vector_coarse_grid_matches_scalar_folded_search(probe: np.ndarray) -> None:
    template = np.asarray(qin_edge_pilot_frame(_RATE, "lower"), np.complex128)
    cfo_grid = (-80_000.0, 0.0, 80_000.0)
    epoch_count = round(_RATE / 750.0)
    expected = tuple(
        _folded_anchor_scores(
            probe,
            template,
            _RATE,
            cfo,
            DEFAULT_ANCHOR_SYMBOLS,
            epoch_count,
        )
        for cfo in cfo_grid
    )
    actual = _folded_anchor_score_grid(
        probe,
        template,
        _RATE,
        cfo_grid,
        DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
    )
    for expected_scores, actual_scores in zip(expected, actual, strict=True):
        np.testing.assert_allclose(actual_scores, expected_scores, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("epoch_sample", [-30, 0, 3_332, 45_000, 49_900])
@pytest.mark.parametrize(
    "symbols",
    [
        np.arange(2, 18),
        np.arange(2, 66),
        np.arange(2, 302),
        np.asarray([10, 20, 30]),
    ],
)
def test_shared_correlations_match_scalar_at_epoch_boundaries(
    probe: np.ndarray,
    epoch_sample: int,
    symbols: np.ndarray,
) -> None:
    workspace = _conditioned_correlation_workspace(
        probe, _RATE, epoch_sample, 12_345.5
    )
    for symbol_roll, control in ((0, False), (CONTROL_SYMBOL_ROLL, True)):
        expected = _symbol_correlations(
            probe,
            _RATE,
            epoch_sample,
            12_345.5,
            symbols,
            symbol_roll=symbol_roll,
        )
        actual = workspace.select(symbols, control=control)
        np.testing.assert_allclose(actual.values, expected.values, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(
            actual.normalized_power,
            expected.normalized_power,
            rtol=1e-12,
            atol=1e-12,
        )
        np.testing.assert_array_equal(actual.times_s, expected.times_s)

    scalar_exact = _symbol_correlations(
        probe,
        _RATE,
        epoch_sample,
        12_345.5,
        symbols,
        symbol_roll=0,
    )
    scalar_control = _symbol_correlations(
        probe,
        _RATE,
        epoch_sample,
        12_345.5,
        symbols,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    paired = _glrt_pair(workspace.select(symbols), workspace.select(symbols, control=True))
    np.testing.assert_allclose(
        paired,
        (_glrt(scalar_exact), _glrt(scalar_control)),
        rtol=1e-9,
        atol=1e-9,
    )
