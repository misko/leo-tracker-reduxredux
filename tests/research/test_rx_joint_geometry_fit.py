import numpy as np
import pytest

from tools.rx_empirical_signal import paired_relative_log_likelihood
from tools.rx_joint_geometry_fit import calibration_score, fit_arms
from tools.rx_presence_filter import forward_score


def _lane(windows, nominees, times, tiny=False):
    rng = np.random.default_rng(windows * 10 + nominees)
    counts = rng.integers(1, 4, size=(windows, 2))
    rates = np.array([1.2, 0.9])
    count_logs = np.full((windows, 2, 2), -np.inf)
    for index, (left, right) in enumerate(counts):
        for signal0 in (0, 1):
            for signal1 in (0, 1):
                shifted = (left - signal0, right - signal1)
                count_logs[index, signal0, signal1] = sum(
                    -rate + count * np.log(rate) - __import__("math").lgamma(count + 1)
                    for count, rate in zip(shifted, rates, strict=True)
                )
    prior = np.full(nominees, -np.log(nominees))
    if tiny and nominees > 1:
        prior = np.array([0.0, -2_000.0, *([-3.0] * (nominees - 2))])
        prior -= np.logaddexp.reduce(prior)
    return {
        "x": rng.normal(size=(windows, nominees, 2, 8)),
        "log_count_probabilities": count_logs,
        "signal": rng.uniform(0.2, 4.0, size=(windows, nominees, 2)),
        "counts": counts,
        "visible": rng.random((windows, nominees)) > 0.15,
        "prior": prior,
        "times": np.asarray(times, dtype=float),
    }


def test_batched_score_matches_existing_lane_forward_with_variable_shapes() -> None:
    lanes = [
        _lane(3, 2, [0.0, 0.2, 4.0], tiny=True),
        _lane(5, 4, [1.0, 1.0, 1.7, 9.0, 20.0]),
        _lane(2, 1, [3.0, 30.0]),
    ]
    beta = np.array([-0.4, 0.2, 0.1, -0.3])
    expected = 0.0
    for lane in lanes:
        logits = lane["x"][..., : len(beta)] @ beta
        relative = paired_relative_log_likelihood(
            lane["log_count_probabilities"],
            lane["signal"],
            lane["counts"],
            logits,
            lane["visible"],
        )
        emissions = np.column_stack((np.zeros(len(relative)), relative))
        size = len(relative)
        score = forward_score(
            lane["prior"],
            emissions,
            lane["times"],
            np.ones(size, dtype=bool),
            np.zeros(size, dtype=bool),
            0.37,
            2.3,
        )
        expected += score.window_log_scores.sum()
    assert calibration_score(lanes, beta, 0.37, 2.3) == pytest.approx(expected, abs=2e-13)


def test_zero_occupancy_is_exact_relative_null() -> None:
    lane = _lane(4, 3, [0.0, 1.0, 2.0, 8.0], tiny=True)
    assert calibration_score([lane], np.zeros(3), 0.0, 1.0) == pytest.approx(0.0)


def test_fit_arms_keeps_null_when_optimizer_gain_is_nonpositive(monkeypatch) -> None:
    import tools.rx_joint_geometry_fit as joint

    class Result:
        success = True
        message = "synthetic convergence"
        nit = 1
        nfev = 1

        def __init__(self, x):
            self.x = np.asarray(x)
            self.fun = 1.0

    starts = []

    def minimize(function, start, **kwargs):
        starts.append(np.asarray(start).copy())
        return Result(start)

    monkeypatch.setattr(joint, "minimize", minimize)
    monkeypatch.setattr(joint, "calibration_score", lambda lanes, beta, occupancy, tau: 0.0)
    result = fit_arms([object()], {"D": {"parameters": [0.0, 0.0, 0.0]}})
    for arm in ("D", "E", "S", "T"):
        assert result["fits"][arm]["selected"]["null_selected"] is True
        assert result["fits"][arm]["selected"]["occupancy"] == 0.0
        assert result["fits"][arm]["selected"]["map_penalty"] == 0.0
        assert len(result["fits"][arm]["candidates"]) == 2
    np.testing.assert_array_equal(starts[3], np.zeros(6))


def test_nested_start_inherits_selected_beta_and_nuisance(monkeypatch) -> None:
    import tools.rx_joint_geometry_fit as joint

    starts = []

    class Result:
        success = True
        message = "synthetic convergence"
        nit = 1
        nfev = 1
        fun = -1.0

        def __init__(self, start):
            self.x = np.asarray(start).copy()
            self.x[-2:] = [0.8, -0.3]

    def minimize(function, start, **kwargs):
        starts.append(np.asarray(start).copy())
        return Result(start)

    monkeypatch.setattr(joint, "minimize", minimize)
    monkeypatch.setattr(joint, "calibration_score", lambda lanes, beta, occupancy, tau: 2.0)
    fit_arms([object()], {"D": {"parameters": [1.0, 2.0, 3.0]}})
    np.testing.assert_array_equal(starts[3], [-2.0, 0.0, 0.0, 0.0, 0.8, -0.3])


def test_fit_arms_raises_when_both_starts_fail(monkeypatch) -> None:
    import tools.rx_joint_geometry_fit as joint

    class Result:
        success = False
        message = "failed"
        nit = 0
        nfev = 1
        fun = 1.0

        def __init__(self, x):
            self.x = np.asarray(x)

    monkeypatch.setattr(joint, "minimize", lambda function, start, **kwargs: Result(start))
    monkeypatch.setattr(joint, "calibration_score", lambda lanes, beta, occupancy, tau: 0.0)
    with pytest.raises(RuntimeError, match="no D optimizer start converged"):
        fit_arms([object()], {"D": {"parameters": [0.0, 0.0, 0.0]}})
