import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from tools.pipeline_eval.variants import algo08_family_profile as profile
from tools.pipeline_eval.variants.algo08_family_profile import (
    BIAS_SIGMA_HZ,
    FamilyProfile,
    eliminate_track_offsets,
    propose,
    ridge_profile,
)


def test_track_profile_matches_explicit_offset_covariance():
    values = np.random.default_rng(4).normal(size=(7, 4))
    group = np.repeat([0, 1, 2], [3, 3, 1])
    slices = [slice(0, 3), slice(3, 6), slice(6, 7)]
    noise = 40.
    covariance = noise**2 * np.eye(7) + BIAS_SIGMA_HZ**2 * (group[:, None] == group)
    transformed = eliminate_track_offsets(values, slices, noise)
    expected = values.T @ np.linalg.solve(covariance, values)
    assert transformed.T @ transformed == pytest.approx(expected)


def test_calibration_arms_profile_the_same_rows_and_nested_design():
    rng = np.random.default_rng(41)
    design = rng.normal(size=(17, 5))
    response = design[:, -1] * 5. + rng.normal(size=17)
    gram, rhs = design.T @ design, design.T @ response
    fitted_score, fitted = ridge_profile(gram, rhs, response @ response)
    fixed_score, _ = ridge_profile(gram[:-1, :-1], rhs[:-1], response @ response)
    residual = response - design @ fitted
    assert fitted_score == pytest.approx(residual @ residual + fitted @ fitted)
    assert fitted_score < fixed_score


def test_low_support_requests_fallback():
    result = propose(dict(status="inputs_prepared", tracks={"tracks": []}), SearchRegion((20., 0.)))
    assert result == {"fallback": ["track_or_catalogue_support"]}


def test_grid_refines_both_arms_on_disjoint_family_scores():
    model = object.__new__(FamilyProfile)
    model.region = SearchRegion((20., 0.))
    endpoints = np.array([[(2., -4.), (2.3, -4.)], [(1., -5.), (1., -5.1)],
                          [(2.5, -3.), (2.5, -3.2)]])

    def evidence(point):
        assert np.max(np.abs(point)) <= model.region.half_width_km
        return dict(scores=np.sum((endpoints - point)**2, axis=-1), visible=True)

    model.at = evidence
    for part, paired in enumerate(model.minimize()):
        for arm, (point, _, gap) in enumerate(paired):
            assert point == pytest.approx(endpoints[part, arm], abs=.1)
            assert gap > 30.


def test_boundary_ambiguous_owners_and_independent_split_trigger_stock(monkeypatch):
    times = np.arange(0., 50., 10.)
    tracks = [dict(times=times, values=10. * times**2) for _ in range(6)]
    prepared = dict(status="inputs_prepared", tracks={"tracks": tracks},
                    sky={"bank": {"norad": np.arange(6)}},
                    noise={"constant_radio_sigma_hz": 150.})
    monkeypatch.setattr(profile, "nominate", lambda *args: [
        (track, index, 0, 2. if index < 2 else 12.) for index, track in enumerate(tracks)
    ])

    class WeakFit:
        cache = {}

        def __init__(self, *args):
            pass

        def minimize(self):
            return [[(np.array(point), 10., 12.)] * 2
                    for point in ((12.5, 0.), (-2., 0.), (2., 0.))]

        def at(self, point):
            return dict(phases=[1., 0.], rms=[1., 0.])

    monkeypatch.setattr(profile, "FamilyProfile", WeakFit)
    result = propose(prepared, SearchRegion((20., 0.)))
    assert set(result["fallback"]) == {
        "ambiguous_or_unmatched_ownership", "c0_split_disagreement", "c0_boundary",
        "fitted_c_split_disagreement", "fitted_c_boundary",
    }
