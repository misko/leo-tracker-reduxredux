"""Quick component checks with synthetic data and no archive dependencies."""

import unittest

import numpy as np
from scipy.optimize import lsq_linear

from compact import (K, PACKED, QUANTUM, SAMPLES, STEP_S, Table,
                     bounded_profile, cold, moments, phase_cost, tile_features, track_candidates)


def run_checks():
    rng = np.random.default_rng(721)
    knots = np.arange(-STEP_S, 65., STEP_S)
    n_sat = 43
    ids = np.arange(1000, 1000 + n_sat)
    f0 = np.linspace(-112000.11, 115000.12, n_sat)
    slope = rng.uniform(-1000, 1000, n_sat)
    curve = rng.uniform(-4, 4, n_sat)

    def frequency(t):
        return f0[:, None] + slope[:, None]*t + curve[:, None]*t*t

    fields = (frequency(knots), rng.uniform(-200, 200, (n_sat, len(knots))),
              rng.uniform(-200, 200, (n_sat, len(knots))), np.full((n_sat, len(knots)), .417))
    compact = Table.create(fields, ids, knots[0], packed=True)
    double = Table.create(fields, ids, knots[0], packed=False)
    assert PACKED.itemsize == 10
    assert compact.cells.tobytes()[:4] == int(round(fields[0][0, 0] / QUANTUM[0])).to_bytes(4, "little", signed=True)
    times = np.linspace(.15, 50.74, SAMPLES)
    plan = compact.index(times)
    f, _, _, _, rate = double.at(np.arange(n_sat), plan)
    np.testing.assert_allclose(f, frequency(times), atol=1e-9, rtol=0)
    np.testing.assert_allclose(rate, slope[:, None] + 2*curve[:, None]*times, atol=1e-9, rtol=0)
    for i, (compact_i, reference_i) in enumerate(zip(compact.at(np.arange(n_sat), plan),
                                                     double.at(np.arange(n_sat), plan), strict=True)):
        weights = plan[2] if i == 4 else plan[1]
        bound = .5*QUANTUM[i % 4]*np.abs(weights).sum(axis=1) + 1e-9
        assert np.all(np.abs(compact_i-reference_i) <= bound)
    try:
        compact.index(np.array([knots[0]]))
    except ValueError:
        pass
    else:
        raise AssertionError("missing rejection before interpolation support")
    try:
        Table.create((fields[0], fields[1]*100, fields[2], fields[3]), ids, knots[0], packed=True)
    except ValueError:
        pass
    else:
        raise AssertionError("missing quantization overflow rejection")

    # Verify incremental candidate trimming against a single full sort.
    all_rows = np.arange(n_sat)
    observed = f[25] + rng.normal(size=SAMPLES)
    raw, _ = tile_features(compact, all_rows, plan, observed, cold.CARRIER)
    stat = moments(raw)
    shape = phase_cost(stat, 0, 0, 0, shape_only=True)
    mean_ref, cov_ref = cold.tile_stats(raw)
    np.testing.assert_allclose(phase_cost(stat, 3., 6., 5.), cold.phase_cost(mean_ref, cov_ref, 3., 6., 5.),
                               atol=1e-8)
    combined = shape + np.maximum(1., np.abs(cold.wrap(stat[:, 0])) / 12000.)**2
    first = list(np.lexsort((all_rows, shape))[:K//2])
    expected = (first + [i for i in np.lexsort((all_rows, combined)) if i not in first])[:K]
    selected, stats, visible = track_candidates(compact, plan, observed, cold.CARRIER)
    assert visible == n_sat
    np.testing.assert_array_equal(selected, expected)
    np.testing.assert_allclose(stats, stat[expected], atol=1e-9)

    # Check the constrained profile against the full design for interior, edge and corner fits.
    a = rng.normal(size=(120, 9))
    bounds = (np.r_[[-1., -1.], np.full(7, -np.inf)], np.r_[[1., 1.], np.full(7, np.inf)])
    for xy in ((.3, -.6), (-1.5, .6), (1.5, -1.6)):
        b = a @ np.r_[xy, rng.normal(size=7)]
        dense = lsq_linear(a, b, bounds=bounds, method="bvls", tol=1e-12)
        assert dense.success
        np.testing.assert_allclose(bounded_profile(a.T @ a, a.T @ b), dense.x, atol=1e-9)
    return dict(cubic_quadratic_and_derivative="passed", rounding_bounds_and_guards="passed",
                tiled_candidates_equal_full_sort="passed", packed_moments_equal_cold_cost="passed",
                profiled_box_fit_equal_dense_bvls="passed")


class CompactTests(unittest.TestCase):
    def test_compact_controls(self):
        run_checks()


if __name__ == "__main__":
    unittest.main()
