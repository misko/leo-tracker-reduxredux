from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis import frozen_position_prediction as module
from leo.analysis.channel_group_calibration import GroupCalibrationFrame
from leo.analysis.frozen_group_calibration import FrozenGroupCalibration
from leo.analysis.hard60_score import likelihood
from leo.contracts.regional_position import POSITION_SCORES, PositionObservations


def test_frozen_prediction_uses_declared_frequency_port_without_changing_inventory(monkeypatch):
    observations = PositionObservations(
        ("row",),
        np.array([0.0]),
        np.array([250001.0]),
        np.array([1e9]),
        np.array([0]),
        np.array([1]),
        np.ones(1),
    )
    correction = SimpleNamespace(predict=lambda *_: np.zeros(1))
    state = module.FrozenGroupPosition((1, 2, 3), np.zeros(2), np.zeros(3), correction)
    bank = SimpleNamespace(numbers=np.array([1, 2, 3]))
    monkeypatch.setattr(
        module,
        "predict_orbits",
        lambda *_args, **_kwargs: (np.zeros((1, 3)), np.ones((1, 3), bool), None, None),
    )
    seen = []

    def scorer(measured, prediction, visible, score):
        seen.append(measured.copy())
        return likelihood(measured, prediction, visible, score)

    result = module.score_frozen_group_position(
        state, observations, bank, None, POSITION_SCORES["V16"], likelihood_port=scorer
    )
    assert result["window_ids"] == ("row",)
    np.testing.assert_array_equal(seen[0], [250001.0])
    assert result["fitted_held_parameters"] == 0


def test_frozen_prediction_preserves_timings_and_training_rf_center_on_all_held_rows(monkeypatch):
    correction = FrozenGroupCalibration(
        150.0,
        11.5e9,
        GroupCalibrationFrame((0, 1), (0.25, 0.75)),
        np.array([100.0, 2.0, 200.0, 3.0, -600.0]),
        np.zeros((2, 2)),
        np.array([-24000.0, 38000.0]),
        np.empty(0),
        np.empty(0),
        np.empty((2, 0)),
    )
    state = module.FrozenGroupPosition(
        (1001, 1002, 1003), np.array([3.0, 4.0]), np.array([-2.0, 0.0, 2.0]), correction
    )
    obs = PositionObservations(
        ("held-a", "held-b"),
        np.array([200.0, 240.0]),
        np.array([-17500.0, 9800.0]),
        np.array([12e9, 12.5e9]),
        np.array([0, 1]),
        np.array([7, 8]),
        np.ones(2),
    )
    bank = SimpleNamespace(numbers=np.array(state.catalogue_numbers))
    visible = np.array([[True, True, False], [True, False, False]])

    def orbits(bank, observations, prior, point, shifts, **kwargs):
        assert observations is obs
        np.testing.assert_array_equal(point, [3.0, 4.0])
        np.testing.assert_array_equal(shifts, [-2.0, 0.0, 2.0])
        assert kwargs == {"derivatives": False}
        return np.zeros((2, 3)), visible, None, None

    monkeypatch.setattr(module, "predict_orbits", orbits)
    score = POSITION_SCORES["V16"]
    result = module.score_frozen_group_position(state, obs, bank, None, score)
    predicted = correction.predict(obs.times_s, obs.rf_hz, obs.receiver, obs.channel >= 5)[
        :, None
    ] * np.ones((1, 3))
    expected = likelihood(obs.measured_hz, predicted, visible, score)
    assert result["window_ids"] == obs.window_ids and result["windows"] == 2
    assert result["frequency_nll"] == expected.nll
    assert result["prior_penalty"] == result["fitted_held_parameters"] == 0
    assert result["signal_windows"] + result["clutter_windows"] == pytest.approx(2.0)
    cells = result["receiver_group_cells"]
    assert sum(row["windows"] for row in cells.values()) == result["windows"]
    assert sum(row["signal_windows"] for row in cells.values()) == pytest.approx(
        result["signal_windows"]
    )
    assert cells["rx0-low"]["windows"] == 0 and cells["rx0-low"]["signal_fraction"] is None
    assert cells["rx0-high"]["windows"] == 1 and cells["rx1-high"]["windows"] == 1
    with pytest.raises(ValueError, match="identity/order"):
        module.score_frozen_group_position(
            state, obs, SimpleNamespace(numbers=np.array([1002, 1001, 1003])), None, score
        )
    with pytest.raises(ValueError):
        state.satellite_shifts_s[0] = 10.0


def test_candidate_audit_preserves_scores_and_distinguishes_ambiguity_from_clutter(monkeypatch):
    correction = FrozenGroupCalibration(
        0.0,
        1e9,
        GroupCalibrationFrame((), ()),
        np.zeros(5),
        np.zeros((2, 2)),
        np.empty(0),
        np.empty(0),
        np.empty(0),
        np.empty((2, 0)),
    )
    state = module.FrozenGroupPosition((1001, 1002, 1003), np.zeros(2), np.zeros(3), correction)
    obs = PositionObservations(
        ("ambiguous", "one-candidate", "clutter"),
        np.array([1.0, 2.0, 3.0]),
        np.zeros(3),
        np.full(3, 1e9),
        np.array([0, 1, 1]),
        np.array([1, 8, 1]),
        np.ones(3),
    )
    visible = np.array([[True, True, False], [True, False, False], [False, False, False]])
    monkeypatch.setattr(
        module,
        "predict_orbits",
        lambda *_a, **_k: (
            np.zeros((3, 3)),
            visible,
            None,
            None,
        ),
    )
    bank = SimpleNamespace(numbers=np.array(state.catalogue_numbers))
    ordinary = module.score_frozen_group_position(state, obs, bank, None, POSITION_SCORES["V16"])
    replay = module.score_frozen_group_position(
        state,
        obs,
        bank,
        None,
        POSITION_SCORES["V16"],
        candidate_diagnostics=True,
    )
    audit = replay.pop("candidate_diagnostics")
    assert replay == ordinary
    assert audit["windows_candidate_posterior_over_half"] == 1
    assert audit["windows_signal_over_half_but_no_candidate_over_half"] == 1
    rows = audit["candidates"]
    assert [r["catalogue_number"] for r in rows] == list(state.catalogue_numbers)
    assert sum(r["signal_windows"] for r in rows) == pytest.approx(replay["signal_windows"])
    assert rows[2]["signal_windows"] == 0.0 and rows[2]["posterior_rms_hz"] is None
    for label, cell in replay["receiver_group_cells"].items():
        assert sum(r["receiver_group_signal_windows"][label] for r in rows) == pytest.approx(
            cell["signal_windows"]
        )
