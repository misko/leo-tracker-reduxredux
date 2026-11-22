from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v4.native_bound import NativeBound, build
from tools.pipeline_eval.variants import algo08_bound_statistics as variant


def test_native_group_statistics_match_both_calibration_sizes_and_replay_cancellation(tmp_path):
    stock = build(tmp_path / "native")
    library = tmp_path / "statistics.so"
    variant.build(library)
    port = SimpleNamespace(NativeBound=NativeBound)
    rng = np.random.default_rng(478597)
    groups = np.repeat(np.arange(4), [24, 38, 32, 39])
    base = rng.normal(size=(len(groups), 8))
    noise = rng.uniform(40., 120., len(groups))
    ordinary = rng.normal(size=len(groups)) * noise
    powers = np.array([1., 0.4, 0.6, 0.2])
    with variant.group_statistics(port, library) as counts:
        incumbent, candidate = NativeBound(stock), port.NativeBound(stock)
        for width in (7, 8):
            design = base[:, :width]
            response = ordinary + design[:, 0] * 600.
            almost_exact = design.copy()
            almost_exact[:, 0] *= 1e4
            prior = np.arange(width) // 2
            for y, features in ((response, design), (almost_exact[:, 0] * 1e4, almost_exact)):
                expected = incumbent(y, features, noise, groups, powers=powers, prior_groups=prior)
                actual = candidate(y, features, noise, groups, powers=powers, prior_groups=prior)
                assert expected.keys() == actual.keys()
                for key in expected:
                    np.testing.assert_allclose(actual[key], expected[key], rtol=2e-7, atol=2e-8,
                                               err_msg=key)
        incumbent.clear()
    assert port.NativeBound is NativeBound
    assert counts["activated"] == 4
    assert counts["rows_avoided"] > 0
    assert counts["group_fallbacks"] > 0
