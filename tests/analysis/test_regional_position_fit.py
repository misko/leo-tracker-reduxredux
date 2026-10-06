import numpy as np
import pytest
from test_regional_position_score import synthetic_inputs

from leo.analysis.regional_position_fit import fit_position
from leo.analysis.regional_position_score import PositionObjective
from leo.contracts.regional_position import POSITION_SCORES


@pytest.mark.parametrize("name", ["T1AT", "V16"])
def test_fixed_point_profile_and_rf_ablation(name):
    observations, bank, prior = synthetic_inputs()
    objective = PositionObjective(observations, bank, prior, POSITION_SCORES[name])
    start = np.array([3, -5, 100, 0, -100, 0, 35, 0.3, 0, 0], dtype=float)
    fits = []
    for arm in ("fitted-c", "zero-c"):
        seed = start.copy()
        if arm == "zero-c":
            seed[6] = 0
        initial = objective.evaluate(seed)[0]
        fit = fit_position(objective, start, rf_arm=arm, fixed_position=True, maximum_seconds=10)
        assert fit.objective < initial
        np.testing.assert_array_equal(fit.vector[:2], start[:2])
        assert fit.posterior_rms_hz < 100
        assert 0 <= fit.signal_windows <= len(observations.window_ids)
        assert fit.stationarity >= 0 and np.isfinite(fit.stationarity)
        if arm == "zero-c":
            assert fit.vector[6] == 0
        fits.append(fit)
    assert objective.observations is observations  # no per-arm selection
    assert fits[0].objective <= fits[1].objective + 1e-5


def test_continuous_fit_keeps_both_disks_and_timing_bounds():
    observations, bank, prior = synthetic_inputs()
    objective = PositionObjective(observations, bank, prior, POSITION_SCORES["V16"])
    start = np.array([3.1, -5.2, 0, 0, 0, 0, 0, 0.3, 0, 0], dtype=float)
    fit = fit_position(
        objective, start, maximum_seconds=10, local_center=start[:2], local_radius_km=1
    )
    assert np.linalg.norm(fit.vector[:2] - start[:2]) <= 1 + 1e-6
    assert np.linalg.norm(fit.vector[:2]) <= prior.radius_km
    assert abs(fit.vector[7]) <= 10
    assert np.max(abs(fit.vector[7] + objective.basis @ fit.vector[8:])) <= 20 + 1e-6
    assert fit.objective <= objective.evaluate(start)[0]


def test_deadline_is_not_success_and_bad_bounds_fail():
    observations, bank, prior = synthetic_inputs()
    objective = PositionObjective(observations, bank, prior, POSITION_SCORES["V16"])
    with pytest.raises(TimeoutError):
        fit_position(objective, np.zeros(objective.size), maximum_seconds=1e-12)
    with pytest.raises(ValueError, match="outside prior"):
        fit_position(objective, np.r_[300, np.zeros(objective.size - 1)])
    with pytest.raises(ValueError, match="local center"):
        fit_position(objective, np.zeros(objective.size), local_radius_km=10)
