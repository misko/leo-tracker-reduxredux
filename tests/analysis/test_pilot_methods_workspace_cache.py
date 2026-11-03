from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink import pilot_methods
from leo.analysis.starlink.pilot_methods import (
    _conditioned_correlation_workspace,
    _symbol_correlations,
)
from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, StarlinkEdge


@pytest.mark.parametrize("sample_rate_hz", [2_500_000, 5_000_000, 7_500_000, 10_000_000])
@pytest.mark.parametrize("edge", [StarlinkEdge.LOWER, StarlinkEdge.UPPER])
def test_cached_workspace_geometry_matches_scalar_correlations(sample_rate_hz, edge) -> None:
    generator = np.random.default_rng(sample_rate_hz + (0 if edge is StarlinkEdge.LOWER else 1))
    samples = np.asarray(
        generator.normal(size=sample_rate_hz // 50)
        + 1j * generator.normal(size=sample_rate_hz // 50),
        dtype=np.complex128,
    )
    symbols = np.arange(2, 66)
    actual = _conditioned_correlation_workspace(
        samples, sample_rate_hz, 37, 12_345.5, edge=edge, selected_symbols=symbols
    )
    for symbol_roll, control in ((0, False), (CONTROL_SYMBOL_ROLL, True)):
        expected = _symbol_correlations(
            samples,
            sample_rate_hz,
            37,
            12_345.5,
            symbols,
            edge=edge,
            symbol_roll=symbol_roll,
        )
        received = actual.select(symbols, control=control)
        np.testing.assert_allclose(received.values, expected.values, rtol=1e-11, atol=3e-12)
        np.testing.assert_allclose(
            received.normalized_power, expected.normalized_power, rtol=1e-11, atol=3e-12
        )
        np.testing.assert_array_equal(received.times_s, expected.times_s)


def test_workspace_geometry_reuses_immutable_templates_per_rate_and_edge(monkeypatch) -> None:
    original = pilot_methods.qin_edge_pilot_frame
    calls = []

    def counted(sample_rate_hz, edge, *, symbol_roll=0):
        calls.append((sample_rate_hz, edge, symbol_roll))
        return original(sample_rate_hz, edge, symbol_roll=symbol_roll)

    pilot_methods._conditioned_workspace_geometry.cache_clear()
    monkeypatch.setattr(pilot_methods, "qin_edge_pilot_frame", counted)
    try:
        first = pilot_methods._conditioned_workspace_geometry(2_500_000, StarlinkEdge.LOWER)
        second = pilot_methods._conditioned_workspace_geometry(2_500_000, StarlinkEdge.LOWER)
        other_edge = pilot_methods._conditioned_workspace_geometry(2_500_000, StarlinkEdge.UPPER)
        assert first is second
        assert len(calls) == 4
        assert not first.symbols.flags.writeable
        assert not first.groups[0].exact_reference.flags.writeable
        assert other_edge is not first
    finally:
        pilot_methods._conditioned_workspace_geometry.cache_clear()
