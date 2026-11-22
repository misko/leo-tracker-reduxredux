from collections import Counter

import numpy as np
import pytest

from leo.analysis import graph_tracklets as graph
from leo.analysis import polynomial_tracklets as poly
from tools.pipeline_eval.variants.experimental.graph_alias import (
    LIFT_EVIDENCE,
    canonical_alias_proposals,
    canonical_proposals,
    relative_winding,
)


def recorded_fit(t, lifted, indices, degree):
    piece = poly._piece(t, lifted, indices, degree)
    piece[LIFT_EVIDENCE] = (indices, lifted)
    return piece


def test_same_fit_canonicalized_across_roundoff_and_uniform_alias_gauge():
    cfg = poly.TrackConfig(alias_spacing_hz=2**17)
    t = np.arange(32, dtype=float)
    ix = np.arange(len(t))
    truth = 60000.0 + 512 * t
    raw = poly._wrap(truth, cfg.alias_spacing_hz)
    translated = truth + 2 * cfg.alias_spacing_hz
    tiny_ulp = np.nextafter(truth, np.inf)
    before = [recorded_fit(t, values, ix, 1) for values in (tiny_ulp, translated, truth)]
    metrics = Counter()
    result = canonical_proposals(t, raw, before, cfg, metrics)
    assert metrics == {"canonical_groups": 1, "duplicate_proposals": 2}
    assert len(result) == 1
    expected = poly._piece(t, truth, ix, 1)
    assert result[0]["coefficients_hz"].tobytes() == expected["coefficients_hz"].tobytes()
    assert LIFT_EVIDENCE not in result[0]


def test_different_degrees_supports_and_relative_lifts_stay_distinct():
    cfg = poly.TrackConfig(alias_spacing_hz=2**17)
    t = np.arange(32, dtype=float)
    raw = 100 * t
    ix = np.arange(len(t))
    different_lifts = raw.copy()
    different_lifts[ix[-1]] += cfg.alias_spacing_hz
    originals = [recorded_fit(t, values, rows, degree) for values, rows, degree in (
        (raw, ix, 1), (different_lifts, ix, 1), (raw, ix, 2), (raw[1:], ix[1:], 1),
    )]
    metrics = Counter()
    result = canonical_proposals(t, raw, originals, cfg, metrics)
    assert not metrics
    assert len(result) == len(originals)
    for a, b in zip(result, originals, strict=True):
        assert a["coefficients_hz"].tobytes() == b["coefficients_hz"].tobytes()


def test_uncertain_lifts_and_unbound_fit_provenance_fall_back():
    assert relative_winding(np.array([3.0]), np.array([67.0]), 128.0) is None
    huge = np.array([float(2**56)])
    assert relative_winding(huge, huge, 128.0) is None
    cfg = poly.TrackConfig()
    t = np.arange(16, dtype=float)
    ix = np.arange(len(t))
    tracked = recorded_fit(t, t, ix, 1)
    stale = recorded_fit(t, t, ix, 1)
    stale[LIFT_EVIDENCE] = (ix[::-1], t)
    assert len(canonical_proposals(t, t, [tracked, stale], cfg, Counter())) == 2


def test_context_restores_the_original_functions_even_after_error():
    fit_piece, finish = poly._piece, graph.finish_lane
    with pytest.raises(RuntimeError, match="trial"):
        with canonical_alias_proposals():
            assert (poly._piece, graph.finish_lane) != (fit_piece, finish)
            raise RuntimeError("trial")
    assert (poly._piece, graph.finish_lane) == (fit_piece, finish)
