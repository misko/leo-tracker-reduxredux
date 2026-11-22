from collections import Counter

import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import BIAS, NOISE, PERIOD, whitening
from tools.pipeline_eval.variants.algo08_nomination_bound import (
    INNOVATION_SLACK,
    _score_radius,
    lower_scores,
    subset_nomination,
    witness_indexes,
)
from tools.pipeline_eval.variants.algo08_streamed_nomination import white_nomination


def exact(y, f, visible, white):
    j, costs, aliases, bias, rms, innovations = white_nomination(y, f, visible, white)
    return j, costs[j], aliases[j], bias, rms, innovations


def signature(row):
    return row[0], tuple(np.asarray(value).tobytes() for value in row[1:])


@pytest.mark.parametrize("order", ["C", "F"])
def test_subset_relaxes_the_full_alias_and_keeps_the_full_normalizer(order):
    rng = np.random.default_rng(1231)
    count = 201
    nodes = witness_indexes(count)
    y = rng.uniform(-20000., 20000., count)
    f = np.array(rng.uniform(-2**24, 2**24, size=(228, count)), order=order)
    f[:3] = y + 100.
    # The four rows and the original full mean choose different aliases.
    f[0, nodes] += PERIOD
    f[1, nodes] += PERIOD / 2
    inverse, volume = whitening(np.arange(count))
    one = np.diag(inverse)
    lower = lower_scores(y[nodes], f[:, nodes], np.log1p(BIAS**2 * (one @ one)))
    _, costs, aliases, *_ = white_nomination(y, f, np.ones(len(f), bool), (inverse, volume))
    assert aliases[0] == 0
    assert np.rint(-(y[nodes] - f[0, nodes]).mean() / PERIOD) == 1
    assert np.all(lower <= costs)


@pytest.mark.parametrize("order", ["C", "F"])
def test_shape_changing_subset_preserves_the_original_winner_on_clear_candidates(order):
    ts = np.arange(41, dtype=float)
    y = (ts - 10)**2 + 1000 * ts
    f = np.array(y + np.arange(21)[:, None] * 1500. * (ts - 10), order=order)
    f[0] += np.cos(ts)
    visible = np.ones(len(f), bool)
    white = whitening(ts)
    measured = Counter()
    actual = subset_nomination(y, f, visible, white, measured)
    original = exact(y, f, visible, white)
    assert (actual[0], actual[2]) == (original[0], original[2])
    assert abs(actual[1] - original[1]) <= _score_radius(original[1], len(y))
    # NumPy may choose another GEMV reduction when the outer shape changes.
    # Exact emitted diagnostics require an original-shape repair.
    np.testing.assert_allclose(
        np.r_[actual[3], actual[4], actual[5]],
        np.r_[original[3], original[4], original[5]],
        rtol=0, atol=4 * INNOVATION_SLACK * NOISE,
    )
    assert measured["full_candidates"] < len(f)


@pytest.mark.parametrize("case", ["tie", "invisible", "correlated", "alias"])
def test_round_ties_and_nonwhite_or_boundary_cases_use_the_original(case):
    ts = np.arange(41, dtype=float)
    y = 14000 * np.sin(ts / 5)
    f = np.array([y, y, y + 100.], order="F")
    white = whitening(ts, correlated_sigma_hz=150 if case == "correlated" else 0)
    eligible = np.ones(len(f), bool)
    if case == "invisible":
        eligible[:] = False
    if case == "alias":
        f[:] += PERIOD / 2
    metrics = Counter()
    assert signature(subset_nomination(y, f, eligible, white, metrics)) == signature(
        exact(y, f, eligible, white),
    )
    assert any(name.startswith("fallback_") and n == 1 for name, n in metrics.items())
