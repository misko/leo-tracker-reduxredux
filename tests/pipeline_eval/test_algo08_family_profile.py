import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from tools.pipeline_eval.variants.algo08_family_profile import (
    BIAS_SIGMA_HZ,
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
