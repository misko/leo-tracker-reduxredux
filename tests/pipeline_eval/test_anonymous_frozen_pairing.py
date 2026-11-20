import numpy as np
import pytest

from tools.pipeline_eval.qualification import anonymous_frozen_pairing as trial
from tools.pipeline_eval.qualification import anonymous_frozen_pairing_solver as solver


def test_pair_bias_and_identity_freeze_before_any_late_sample():
    true = np.arange(12.0) ** 2
    alternate = true.copy()
    alternate[8:] += 250
    predicted = (np.array([true, alternate]), np.zeros((1, 12)))
    visible = (np.ones((2, 12), bool), np.ones((1, 12), bool))
    ids = (np.array([11, 12]), np.array([30]))
    observed = true + 20000
    options = solver.candidates(predicted, visible, ids, observed, 8)
    late_bias = observed.copy()
    late_bias[8:] += 400
    new = solver.candidates(predicted, visible, ids, late_bias, 8)

    assert [(x.rows, x.bias_hz, x.early_mse) for x in options] == [
        (x.rows, x.bias_hz, x.early_mse) for x in new
    ]
    assert options[0].rows == (11, 30)
    assert options[0].late_mse == 0
    assert options[1].late_mse == 250 ** 2
    assert new[0].bias_hz == 20000
    assert new[0].late_mse == 400 ** 2


def test_late_null_preserves_the_early_checksum_and_simultaneous_samples():
    pair = dict(times=list(range(24)), first_hz=list(range(24)), second_hz=list(range(50, 74)))
    null = trial.late_control(pair)
    assert null["times"] == pair["times"]
    assert trial.early_hash([pair]) == trial.early_hash([null])
    assert null["first_hz"][16:] == [22, 23, 16, 17, 18, 19, 20, 21]
    np.testing.assert_array_equal(np.array(null["second_hz"]) - null["first_hz"], 50)


def test_joint_assignment_requires_four_units_of_independent_orbit_identity():
    a = solver.Assignment((1, 2), 0, 0, 0, 0)
    same = solver.Assignment((2, 3), 0, 0, 0, 0)
    separate = solver.Assignment((3, 4), 0, 0, 0, 0)
    layer = list(solver.joint_trials(np.zeros(2), [[a], [same, separate]]))
    assert [r.names for r in layer] == [((1, 2), (3, 4))]


@pytest.mark.parametrize("alternate_mse, spatial_mse, expected", [
    (20000, 20000, None),
    (4000, 20000, "weak_held_identity_lead"),
    (20000, 4000, "weak_held_position_lead"),
])
def test_late_evidence_checks_same_location_alias_and_far_location_separately(
    alternate_mse, spatial_mse, expected
):
    a = solver.Assignment((1, 2), 5, 1, 10, 30000)
    b = solver.Assignment((3, 4), -8, 2, 10, 30000)
    alternate = solver.Assignment((7, 8), 0, 50000, alternate_mse, 0)
    winner = solver.Trial(np.zeros(2), (a, b), 1.5, 10, 30000)
    other_map = solver.Trial(np.zeros(2), (a, alternate), 10, alternate_mse, 30000)
    distant = solver.Trial(np.array([0, 10]), (a, b), 30, spatial_mse, 30000)
    diagnostic, reason = solver.held_report(winner, [winner, other_map, distant])
    assert reason == expected
    assert diagnostic["trained_pair_offsets_hz"] == [5, -8]


def test_empty_measured_support_withholds_both_calibration_arms():
    output = solver.solve({"pairs": []}, "unread", tile=[0, 0])
    assert output["status"] == "withheld"
    assert output["arms"]["c0"] == output["arms"]["fitted_c"]
    assert output["arms"]["c0"]["latlon"] is None
