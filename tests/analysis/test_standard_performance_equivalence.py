from __future__ import annotations

import numpy as np
import pytest

import leo.analysis.starlink.acquisition as acquisition
from leo.analysis.starlink.acquisition import (
    DEFAULT_ACQUIRE_SYMBOLS,
    DEFAULT_ANCHOR_SYMBOLS,
    _cached_dense_rotation_bank,
    _conditioned_frame_scores,
    _folded_anchor_score_grid,
    _folded_anchor_scores,
    _folded_anchor_scores_derotated,
    _folded_anchor_scores_derotated_native,
    _folded_anchor_scores_derotated_python,
    _normalized_frame_scores,
    _power_prefix,
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
    StarlinkEdge,
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
        normalized_frame_score(probe, template, _RATE, 347, cfo, DEFAULT_ACQUIRE_SYMBOLS)[0]
        for cfo in cfo_grid
    )
    expected_conditioned = tuple(
        conditioned_frame_score(probe, template, _RATE, 347, cfo)[0] for cfo in cfo_grid
    )

    np.testing.assert_allclose(
        _normalized_frame_scores(probe, template, _RATE, 347, cfo_grid, DEFAULT_ACQUIRE_SYMBOLS),
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


def test_coarse_rotation_bank_is_immutable_and_reused() -> None:
    cfo_grid = (-80_000.0, 0.0, 80_000.0)

    first = _cached_dense_rotation_bank(_RATE, 50_000, cfo_grid)
    second = _cached_dense_rotation_bank(_RATE, 50_000, cfo_grid)

    assert second is first
    assert first.flags.writeable is False


@pytest.mark.parametrize("sample_count", [4_000, 49_987, 50_000])
@pytest.mark.parametrize("signal", ["zero", "noise", "tone"])
def test_native_folded_anchor_matches_python_oracle(
    sample_count: int,
    signal: str,
) -> None:
    assert acquisition._native_acquisition is not None
    template = np.asarray(qin_edge_pilot_frame(_RATE, "lower"), np.complex128)
    if signal == "zero":
        probe = np.zeros(sample_count, dtype=np.complex128)
    elif signal == "noise":
        generator = np.random.default_rng(0xC0FFEE + sample_count)
        probe = generator.normal(size=sample_count) + 1j * generator.normal(size=sample_count)
    else:
        time_s = np.arange(sample_count, dtype=float) / _RATE
        probe = np.exp(2j * np.pi * 123_456.75 * time_s)
    epoch_count = min(round(_RATE / 750.0), sample_count)
    prefix = _power_prefix(probe)

    expected = _folded_anchor_scores_derotated_python(
        probe,
        template,
        _RATE,
        DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
        power_prefix=prefix,
    )
    actual = _folded_anchor_scores_derotated_native(
        probe,
        template,
        _RATE,
        DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
        power_prefix=prefix,
    )
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_folded_anchor_falls_back_to_python_oracle(monkeypatch: pytest.MonkeyPatch) -> None:
    generator = np.random.default_rng(0xFA11BAC)
    probe = generator.normal(size=8_000) + 1j * generator.normal(size=8_000)
    template = np.asarray(qin_edge_pilot_frame(_RATE, "lower"), np.complex128)
    epoch_count = 512
    expected = _folded_anchor_scores_derotated_python(
        probe,
        template,
        _RATE,
        DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
    )

    monkeypatch.setattr(acquisition, "_native_acquisition", None)
    actual = _folded_anchor_scores_derotated(
        probe,
        template,
        _RATE,
        DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
    )
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=0.0)


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
        probe, _RATE, epoch_sample, 12_345.5, edge=StarlinkEdge.LOWER
    )
    for symbol_roll, control in ((0, False), (CONTROL_SYMBOL_ROLL, True)):
        expected = _symbol_correlations(
            probe,
            _RATE,
            epoch_sample,
            12_345.5,
            symbols,
            edge=StarlinkEdge.LOWER,
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
        edge=StarlinkEdge.LOWER,
        symbol_roll=0,
    )
    scalar_control = _symbol_correlations(
        probe,
        _RATE,
        epoch_sample,
        12_345.5,
        symbols,
        edge=StarlinkEdge.LOWER,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    paired = _glrt_pair(workspace.select(symbols), workspace.select(symbols, control=True))
    np.testing.assert_allclose(
        paired,
        (_glrt(scalar_exact), _glrt(scalar_control)),
        rtol=1e-9,
        atol=1e-9,
    )
