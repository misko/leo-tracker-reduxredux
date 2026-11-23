from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.graph_tracklets import _graph
from leo.analysis.polynomial_tracklets import TrackConfig
from reports.ALGO08.v3.vector_graph_edges import ordered_edges


@pytest.mark.parametrize("size", [0, 1, 32, 145])
@pytest.mark.parametrize("period", [4000.0, 227272.727])
def test_ordered_edge_values_aliases_adjacency_and_ties(size, period):
    rng = np.random.default_rng(1781)
    t = np.sort(rng.choice(np.arange(160) * 0.15, size=size, replace=True))
    y = np.round(rng.normal(0, 14000, size) / 10) * 10
    config = replace(TrackConfig(), max_gap_s=10.0, max_slope_hz_s=1500.0, alias_spacing_hz=period)
    original = _graph(t, y, config)
    actual = ordered_edges(t, y, config, lambda *_: pytest.fail("Unexpected fallback"))
    for before, after in zip(original[:4], actual[:4], strict=True):
        assert before.dtype == after.dtype and before.tobytes() == after.tobytes()
    for orig_rows, new_rows in zip(original[4:], actual[4:], strict=True):
        assert len(orig_rows) == len(new_rows) == size
        for before, after in zip(orig_rows, new_rows, strict=True):
            np.testing.assert_array_equal(before, after)


def test_large_alias_bank_uses_original_path():
    t = np.arange(4, dtype=float)
    assert (
        ordered_edges(t, t, replace(TrackConfig(), alias_spacing_hz=1.0), lambda *_: "original")
        == "original"
    )
