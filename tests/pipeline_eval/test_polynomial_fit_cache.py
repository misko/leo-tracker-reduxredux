"""The lane cache uses full fit inputs and hands mutable outputs to one caller."""

from collections import Counter
import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def cache(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    result = importlib.import_module("polynomial_fit_cache")
    from leo.analysis import polynomial_tracklets as poly
    from leo.analysis.localization_v3 import tracks

    monkeypatch.setattr(result, "installed_sources", lambda: (poly, tracks))
    return result, poly, tracks


def test_effective_lift_exact_bytes_and_mutation_cache_seal(cache, monkeypatch):
    module, poly, tracks = cache
    exact, shape = poly._best_piece, np.arange(12.)
    cfg = poly.TrackConfig(window_lengths_s=[24.])
    counts = Counter()

    def lane(t, y, configuration):
        indices = np.arange(t.size)
        first = poly._best_piece(t, y, indices, y.copy(), configuration)
        expected = exact(t, y, indices, y.copy(), configuration)
        first["indices"][:] = -1
        first["coefficients_hz"][:] = -10.
        hit = poly._best_piece(t, y, indices, y.copy(), configuration)
        assert hit["indices"].tobytes() == expected["indices"].tobytes()
        assert hit["coefficients_hz"].tobytes() == expected["coefficients_hz"].tobytes()
        hit["coefficients_hz"].fill(99.)
        assert poly._best_piece(t, y, indices, y.copy(), configuration)["coefficients_hz"].tobytes() == expected["coefficients_hz"].tobytes()
        one_ulp = y.copy()
        one_ulp[0] = np.nextafter(one_ulp[0], np.inf)
        poly._best_piece(t, y, indices, one_ulp, configuration)
        assert counts["best_hits"] == 2
        configuration.window_lengths_s[0] += 1.
        poly._best_piece(t, y, indices, y.copy(), configuration)
        t[-1] += 1.
        poly._best_piece(t, y, indices, y.copy(), configuration)
        y[-1] *= 2.
        poly._best_piece(t, y, indices, y.copy(), configuration)
        assert counts["best_hits"] == 2

    monkeypatch.setattr(tracks, "fit_lane", lane)
    with module.reuse("best", counts):
        tracks.fit_lane(shape, np.full(12, 6.), cfg)
    assert poly._best_piece is exact and counts["best_calls"] == 7


def test_piece_cache_lifetime_and_ordered_indices(cache, monkeypatch):
    module, poly, tracks = cache
    counts = Counter()

    def lane(t, y, _):
        ids = np.arange(t.size)
        original = poly._piece(t, y, ids, 1)
        original["indices"][0] = -1
        ordinary = poly._piece(t, y, ids, 1)
        assert np.array_equal(ordinary["indices"], ids)
        reverse = poly._piece(t, y, ids[::-1], 1)
        assert np.array_equal(reverse["indices"], ids[::-1])
        poly._piece(t, y, ids, 2)

    monkeypatch.setattr(tracks, "fit_lane", lane)
    exact = poly._piece
    with module.reuse("piece", counts):
        for _ in range(2):
            tracks.fit_lane(np.arange(12.), np.arange(12.) ** 2, poly.TrackConfig())
    assert poly._piece is exact and counts["piece_calls"] == 8 and counts["piece_hits"] == 2


def test_nonfinite_float_payload_and_strides_are_keyed_distinctly(cache):
    module, _, _ = cache
    assert module.array_keys(np.array([+0.])) != module.array_keys(np.array([-0.]))
    base = np.array([1., 99., 2.])
    assert module.array_keys(base[::2]) != module.array_keys(np.array([1., 2.]))
    assert module.array_keys(np.empty(1, dtype=object)) is None
