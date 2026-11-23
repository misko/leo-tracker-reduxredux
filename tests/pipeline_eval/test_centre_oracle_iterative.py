from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    from centre_oracle_iterative import trust_fit

    return trust_fit


def test_exact_profile_refuses_nonimproving_trials_and_relinearizes(trial):
    def profile(point):
        east, north = point
        return np.array([east**2 + east - 2., 3. * (north + .25)]), {}

    result = trial(profile, np.full(2, -12.5), np.full(2, 12.5))
    costs = [h["objective"] for h in result["history"]]
    assert all(a > b for a, b in zip(costs, costs[1:], strict=False))
    assert any(e.get("accepted") is False for e in result["evaluations"])
    assert len(result["evaluations"]) <= 31
    assert result["stopped"] == "small_bounded_step"
    np.testing.assert_allclose(result["history"][-1]["point"], [1., -.25], atol=.020)


def test_stationary_centre_reports_only_two_derivative_checks(trial):
    result = trial(lambda point: (point, {}), np.full(2, -2.), np.full(2, 2.))
    assert result["accepted_steps"] == 0
    assert result["stopped"] == "small_bounded_step"
    assert [e["role"] for e in result["evaluations"]] == ["centre", "derivative", "derivative"]
