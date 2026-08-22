from __future__ import annotations

import numpy as np
import pytest

import leo.analysis.starlink.acquisition as acquisition
from leo.analysis.starlink.acquisition import (
    DEFAULT_ACQUIRE_SYMBOLS,
    DEFAULT_ANCHOR_SYMBOLS,
    _cached_dense_rotation_bank,
    _conditioned_frame_scores,
    _fine_cfo_transform_size,
    _folded_anchor_score_grid,
    _folded_anchor_score_grid_native,
    _folded_anchor_scores,
    _folded_anchor_scores_derotated,
    _folded_anchor_scores_derotated_native,
    _folded_anchor_scores_derotated_python,
    _local_peak_indexes,
    _normalized_frame_scores,
    _normalized_frame_scores_direct,
    _normalized_frame_scores_fft,
    _pilot_sample_indexes,
    _power_prefix,
    conditioned_frame_score,
    normalized_frame_score,
)
from leo.analysis.starlink.pilot_methods import (
    _conditioned_correlation_workspace,
    _glrt,
    _glrt_pair,
    _glrt_pair_autocorrelation,
    _glrt_pair_direct,
    _glrt_pair_fft,
    _symbol_correlations,
    _SymbolCorrelations,
    _uniform_glrt_geometry,
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


@pytest.mark.parametrize(
    ("step_hz", "count", "transform_size"),
    [
        (500.0, 321, 5_000),
        (_RATE / 4_096, 263, 4_096),
        (100.0, 201, 25_000),
        (_RATE / 16_384, 133, 16_384),
    ],
)
def test_exact_fine_cfo_fft_matches_direct_oracle(
    probe: np.ndarray,
    step_hz: float,
    count: int,
    transform_size: int,
) -> None:
    template = np.asarray(qin_edge_pilot_frame(_RATE, "lower"), np.complex128)
    first_hz = -73_456.25
    grid = tuple(first_hz + index * step_hz for index in range(count))

    direct = _normalized_frame_scores_direct(
        probe,
        template,
        _RATE,
        347,
        grid,
        DEFAULT_ACQUIRE_SYMBOLS,
    )
    transformed = _normalized_frame_scores_fft(
        probe,
        template,
        _RATE,
        347,
        grid,
        DEFAULT_ACQUIRE_SYMBOLS,
        transform_size=transform_size,
    )

    np.testing.assert_allclose(transformed, direct, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(
        _normalized_frame_scores(
            probe,
            template,
            _RATE,
            347,
            grid,
            DEFAULT_ACQUIRE_SYMBOLS,
        ),
        direct,
        rtol=1e-12,
        atol=1e-12,
    )
    assert int(np.argmax(transformed)) == int(np.argmax(direct))


def test_fine_cfo_transform_planner_is_exact_and_cost_aware() -> None:
    indexes = _pilot_sample_indexes(_RATE, DEFAULT_ACQUIRE_SYMBOLS)

    current_standard = tuple(-80_000.0 + index * 500.0 for index in range(321))
    aligned_step = _RATE / 4_096
    aligned_standard = tuple(-80_000.0 + index * aligned_step for index in range(263))
    current_research = tuple(-10_000.0 + index * 100.0 for index in range(201))
    irregular = (*current_standard[:100], current_standard[100] + 0.25, *current_standard[101:])

    assert _fine_cfo_transform_size(_RATE, current_standard, indexes) == 5_000
    assert _fine_cfo_transform_size(_RATE, aligned_standard, indexes) == 4_096
    assert _fine_cfo_transform_size(_RATE, current_research, indexes) is None
    assert _fine_cfo_transform_size(_RATE, irregular, indexes) is None
    assert _fine_cfo_transform_size(_RATE, (0.0,), indexes) is None


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


@pytest.mark.parametrize(
    ("sample_rate_hz", "sample_count", "cfo_grid"),
    [
        (2_500_000, 4_000, (-400_000.0, 0.0, 400_000.0)),
        (2_500_000, 49_987, tuple(float(value) for value in range(-400_000, 400_001, 80_000))),
        (2_400_000, 50_000, (-123_456.75, -23_456.75, 76_543.25)),
    ],
)
def test_batched_native_coarse_grid_matches_per_cfo_native_oracle(
    sample_rate_hz: int,
    sample_count: int,
    cfo_grid: tuple[float, ...],
) -> None:
    generator = np.random.default_rng(0xBA7C4 + sample_count)
    values = np.asarray(
        generator.normal(size=sample_count) + 1j * generator.normal(size=sample_count),
        np.complex128,
    )
    template = np.asarray(qin_edge_pilot_frame(sample_rate_hz, "lower"), np.complex128)
    epoch_count = min(round(sample_rate_hz / 750.0), sample_count)
    expected = tuple(
        _folded_anchor_scores(
            values,
            template,
            sample_rate_hz,
            cfo_hz,
            DEFAULT_ANCHOR_SYMBOLS,
            epoch_count,
        )
        for cfo_hz in cfo_grid
    )

    actual = _folded_anchor_score_grid_native(
        values,
        template,
        sample_rate_hz,
        cfo_grid,
        DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    assert tuple(int(np.argmax(row)) for row in actual) == tuple(
        int(np.argmax(row)) for row in expected
    )


def test_coarse_grid_falls_back_when_batch_extension_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = np.random.default_rng(0xFA11BA7C)
    values = np.asarray(
        generator.normal(size=8_000) + 1j * generator.normal(size=8_000),
        np.complex128,
    )
    template = np.asarray(qin_edge_pilot_frame(_RATE, "lower"), np.complex128)
    grid = (-80_000.0, 0.0, 80_000.0)
    epoch_count = 512
    expected = _folded_anchor_score_grid(
        values,
        template,
        _RATE,
        grid,
        DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
    )

    monkeypatch.setattr(acquisition, "_native_acquisition", None)
    actual = _folded_anchor_score_grid(
        values,
        template,
        _RATE,
        grid,
        DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


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


@pytest.mark.parametrize("size", [512, 4_096])
def test_exact_glrt_fft_pair_matches_direct_oracle(probe: np.ndarray, size: int) -> None:
    workspace = _conditioned_correlation_workspace(
        probe,
        _RATE,
        347,
        12_345.5,
        edge=StarlinkEdge.LOWER,
    )
    symbols = np.arange(2, 66)
    exact = workspace.select(symbols)
    control = workspace.select(symbols, control=True)

    direct = _glrt_pair_direct(exact, control, size=size)
    transformed = _glrt_pair_fft(exact, control, size=size)
    autocorrelation = _glrt_pair_autocorrelation(exact, control, size=size)

    assert _uniform_glrt_geometry(exact, size=size)
    np.testing.assert_allclose(transformed, direct, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(autocorrelation, direct, rtol=1e-12, atol=1e-12)
    assert transformed[0][1] == direct[0][1]
    assert transformed[1][1] == direct[1][1]
    assert autocorrelation[0][1] == direct[0][1]
    assert autocorrelation[1][1] == direct[1][1]
    np.testing.assert_allclose(
        _glrt_pair(exact, control, size=size), direct, rtol=1e-12, atol=1e-12
    )


def test_glrt_dispatch_falls_back_for_nonuniform_geometry() -> None:
    values = np.asarray([[1 + 2j, 3 - 4j, -2 + 0.5j]], dtype=np.complex128)
    times = np.asarray([[0.0, 4.4e-6, 9.0e-6]], dtype=float)
    correlations = _SymbolCorrelations(values, np.ones_like(values.real), times)
    control = _SymbolCorrelations(np.conj(values), np.ones_like(values.real), times.copy())

    assert not _uniform_glrt_geometry(correlations, size=512)
    assert _glrt_pair(correlations, control) == _glrt_pair_direct(correlations, control)
    with pytest.raises(ValueError, match="uniform grid"):
        _glrt_pair_fft(correlations, control)


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        (np.asarray([], dtype=float), ()),
        (np.asarray([0.0]), ()),
        (np.asarray([1.0]), (0,)),
        (np.asarray([1.0, 1.0, 0.0, 2.0, 2.0]), (0, 1, 3, 4)),
        (np.asarray([np.nan, 1.0, np.inf, -np.inf]), (2,)),
    ],
)
def test_vectorized_local_peaks_preserve_plateau_and_nonfinite_rules(
    scores: np.ndarray,
    expected: tuple[int, ...],
) -> None:
    assert _local_peak_indexes(scores) == expected
