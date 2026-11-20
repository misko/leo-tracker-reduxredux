import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import PERIOD, profile, whitening
from tools.pipeline_eval.variants import v5_batched_salvage as batched


@pytest.mark.parametrize("correlated_sigma_hz", [0.0, 50.0])
def test_profile_batches_retain_candidate_order_and_all_outputs(monkeypatch, correlated_sigma_hz):
    rng = np.random.default_rng(42)
    times = np.arange(12, dtype=float)
    observed = rng.normal(0, 2000, len(times))
    candidates = rng.normal(0, 8000, (17, 2 * len(times)))[:, ::2]
    candidates[3] = candidates[0]
    candidates[8:11] += PERIOD
    inverse, volume = whitening(times, correlated_sigma_hz=correlated_sigma_hz)
    monkeypatch.setattr(batched, "PREDICTION_BLOCK_BYTES", 5 * candidates.shape[1] * 8)
    rows = []

    def measured(observations, predictions, whitening, logvolume, **kwargs):
        rows.append(len(predictions))
        return profile(observations, predictions, whitening, logvolume, **kwargs)

    actual = batched.bounded_profile(measured, observed, candidates, inverse, volume)
    expected = profile(observed, candidates, inverse, volume)
    assert rows == [5, 5, 5, 2]
    assert actual.keys() == expected.keys()
    np.testing.assert_array_equal(actual["alias"], expected["alias"])
    for name in expected.keys() - {"alias"}:
        np.testing.assert_allclose(actual[name], expected[name], rtol=2e-14, atol=1e-11)
    np.testing.assert_array_equal(np.argsort(actual["cost"]), np.argsort(expected["cost"]))


def test_single_candidate_and_invalid_layout_use_the_original_profile():
    observed = np.array([500.0, 400.0, 300.0])
    inverse = np.eye(len(observed))
    expected = profile(observed, np.zeros_like(observed), inverse)
    actual = batched.bounded_profile(profile, observed, np.zeros_like(observed), inverse)
    for name in expected:
        np.testing.assert_array_equal(actual[name], expected[name])
    with pytest.raises(ValueError, match="matching observations"):
        batched.bounded_profile(profile, observed, np.zeros(4), inverse)
