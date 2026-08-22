from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

import leo.analysis.starlink.acquisition as acquisition
from leo.analysis.starlink.acquisition import DEFAULT_ACQUIRE_SYMBOLS
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace, _glrt_pair_fft
from leo.analysis.starlink.templates import StarlinkEdge, qin_edge_pilot_frame

_RATE = 2_500_000


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "benchmark_glrt_hardware_execution.py"
    spec = importlib.util.spec_from_file_location("glrt_hardware_execution_benchmark", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "scores",
    [
        np.asarray([], dtype=float),
        np.asarray([0.0]),
        np.asarray([1.0]),
        np.asarray([1.0, 1.0, 0.0, 2.0, 2.0]),
        np.asarray([np.nan, 1.0, np.inf, -np.inf]),
    ],
)
def test_vectorized_peak_prototype_preserves_production_rule(scores: np.ndarray) -> None:
    tool = _tool()

    assert tool._local_peak_indexes_vectorized(scores) == acquisition._local_peak_indexes(scores)


def test_factored_matrix_prototypes_match_current_scientific_backends() -> None:
    tool = _tool()
    generator = np.random.default_rng(0xA11CE)
    values = np.asarray(
        generator.normal(size=20_000) + 1j * generator.normal(size=20_000),
        np.complex128,
    )
    template = np.asarray(qin_edge_pilot_frame(_RATE, StarlinkEdge.LOWER), np.complex128)
    normalized_grid = tuple(-10_000.0 + index * 100.0 for index in range(201))
    conditioned_grid = tuple(-1_000.0 + index * 25.0 for index in range(81))

    expected_normalized = acquisition._normalized_frame_scores_direct(
        values,
        template,
        _RATE,
        347,
        normalized_grid,
        DEFAULT_ACQUIRE_SYMBOLS,
    )
    expected_conditioned = acquisition._conditioned_frame_scores(
        values,
        template,
        _RATE,
        347,
        conditioned_grid,
    )

    actual_normalized = tool._normalized_frame_scores_factored(
        values,
        template,
        _RATE,
        347,
        normalized_grid,
        DEFAULT_ACQUIRE_SYMBOLS,
    )
    actual_conditioned = tool._conditioned_frame_scores_factored(
        values,
        template,
        _RATE,
        347,
        conditioned_grid,
    )

    np.testing.assert_allclose(actual_normalized, expected_normalized, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(actual_conditioned, expected_conditioned, rtol=1e-12, atol=1e-12)
    assert int(np.argmax(actual_normalized)) == int(np.argmax(expected_normalized))
    assert int(np.argmax(actual_conditioned)) == int(np.argmax(expected_conditioned))


def test_standard_execution_padding_preserves_eleven_scientific_cfo_rows() -> None:
    tool = _tool()
    generator = np.random.default_rng(0x51AD)
    values = np.asarray(
        generator.normal(size=8_000) + 1j * generator.normal(size=8_000),
        np.complex128,
    )
    template = np.asarray(qin_edge_pilot_frame(_RATE, StarlinkEdge.LOWER), np.complex128)
    grid = tuple(float(value) for value in np.arange(-400_000, 400_001, 80_000))
    epoch_count = 512

    expected = acquisition._folded_anchor_score_grid(
        values,
        template,
        _RATE,
        grid,
        acquisition.DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
    )
    actual = tool._folded_anchor_score_grid_padded(
        values,
        template,
        _RATE,
        grid,
        acquisition.DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
    )

    assert len(actual) == len(grid) == 11
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    assert tuple(int(np.argmax(row)) for row in actual) == tuple(
        int(np.argmax(row)) for row in expected
    )


@pytest.mark.parametrize("size", [512, 4_096])
def test_summed_autocorrelation_prototype_matches_exact_fft(size: int) -> None:
    tool = _tool()
    generator = np.random.default_rng(0xACF + size)
    values = np.asarray(
        generator.normal(size=50_000) + 1j * generator.normal(size=50_000),
        np.complex128,
    )
    workspace = _conditioned_correlation_workspace(
        values,
        _RATE,
        347,
        12_345.5,
        edge=StarlinkEdge.LOWER,
    )
    symbols = np.arange(2, 66)
    exact = workspace.select(symbols)
    control = workspace.select(symbols, control=True)

    expected = _glrt_pair_fft(exact, control, size=size)
    actual = tool._glrt_pair_autocorrelation(exact, control, size=size)

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    assert actual[0][1] == expected[0][1]
    assert actual[1][1] == expected[1][1]


def test_factored_workspace_preserves_correlations_and_method_scores() -> None:
    tool = _tool()
    generator = np.random.default_rng(0xFACE)
    values = np.asarray(
        generator.normal(size=50_000) + 1j * generator.normal(size=50_000),
        np.complex128,
    )
    symbols = np.unique(
        np.concatenate((np.rint(np.linspace(2, 301, 8)).astype(int), np.arange(2, 66)))
    )
    expected = _conditioned_correlation_workspace(
        values,
        _RATE,
        347,
        12_345.5,
        edge=StarlinkEdge.LOWER,
        selected_symbols=symbols,
    )
    actual = tool._conditioned_correlation_workspace_factored(
        values,
        _RATE,
        347,
        12_345.5,
        edge=StarlinkEdge.LOWER,
        selected_symbols=symbols,
    )

    assert tool._workspace_delta(expected, actual)["valid_rows_exact_match"]
    for selected in (np.arange(2, 66), symbols):
        np.testing.assert_allclose(
            actual.select(selected).values,
            expected.select(selected).values,
            rtol=1e-12,
            atol=1e-12,
        )
        np.testing.assert_allclose(
            actual.select(selected, control=True).normalized_power,
            expected.select(selected, control=True).normalized_power,
            rtol=1e-12,
            atol=1e-12,
        )
