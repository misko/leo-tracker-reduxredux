import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import minimize

SPEC = importlib.util.spec_from_file_location(
    "joint_oracle", Path(__file__).with_name("joint_circular_oracle.py"))
ORACLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ORACLE)

FIT_SPEC = importlib.util.spec_from_file_location(
    "joint_fitter_oracle_check",
    Path(__file__).parents[2] / "tools/research/refine_joint_circular_position.py")
FITTER = importlib.util.module_from_spec(FIT_SPEC)
sys.modules[FIT_SPEC.name] = FITTER
FIT_SPEC.loader.exec_module(FITTER)


def accelerated_score(position, arm):
    train, test, nt, ne, offsets, groups = ORACLE.synthetic_scene(position)
    shapes = [FITTER.TrackShape(tr, tr+te, off, null_tr, null_tr+null_te,
                               np.ones(len(tr), dtype=bool))
              for tr, te, null_tr, null_te, off in zip(train, test, nt, ne, offsets, strict=True)]
    return FITTER.score_shape_groups(shapes, groups, arm)


def test_synthetic_position_and_shared_offsets_are_identifiable():
    def loss(position):
        return -ORACLE.dense_group_score(*ORACLE.synthetic_scene(position))[0]
    result = minimize(loss, [1.2, 0.5], method="Powell",
                      options={"xtol": 1e-7, "ftol": 1e-10})
    assert result.success
    np.testing.assert_allclose(result.x, [0.4, -0.7], atol=0.002)


def test_candidate_with_tiny_training_weight_can_dominate_heldout():
    train = [np.log([1-1e-12, 1e-12])]
    test = [np.array([-100., 0.])]
    _, predictive = ORACLE.dense_group_score(
        train, test, [-1000.], [0.], [[0., 0.]], [0])
    np.testing.assert_allclose(predictive, np.log(1e-12), atol=1e-8)
    assert predictive > -30  # Dropping the tiny training candidate would return -100.


def test_all_null_tracks_leave_group_offsets_unidentified():
    training, predictive = ORACLE.dense_group_score(
        [[-np.inf], [-np.inf]], [[-2.], [-3.]], [-4., -5.], [-6., -7.],
        [[123.], [456.]], [0, 0])
    np.testing.assert_allclose([training, predictive], [-9., -13.], atol=1e-12)


@pytest.mark.parametrize("sigma", [3000., 10000., 30000.])
@pytest.mark.parametrize("outlier", [0.05, 0.2])
def test_accelerated_fitter_matches_independent_dense_oracle(sigma, outlier):
    arm = FITTER.CircularArm(sigma, outlier, grid_size=512)
    for position in ([0.4, -0.7], [1.2, 0.5], [-2., 2.]):
        scene = ORACLE.synthetic_scene(position)
        train, heldout = ORACLE.dense_group_score(*scene, sigma=sigma, outlier=outlier)
        actual = accelerated_score(position, arm)
        expected = [train-sum(scene[2]), heldout-sum(scene[3])]
        error = np.max(np.abs(np.array([
            actual["training_score"], actual["heldout_score"]])-expected))
        assert error <= actual["pruning_log_error_bound"] + 1e-10


def test_accelerated_fitter_recovers_injected_position():
    arm = FITTER.CircularArm(3000., 0.05, grid_size=512)
    result = minimize(lambda p: -accelerated_score(p, arm)["training_score"],
                      [1.2, 0.5], method="Powell",
                      options={"xtol": 1e-7, "ftol": 1e-10})
    assert result.success
    np.testing.assert_allclose(result.x, [0.4, -0.7], atol=0.002)
