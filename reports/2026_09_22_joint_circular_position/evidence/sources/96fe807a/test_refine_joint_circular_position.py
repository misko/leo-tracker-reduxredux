import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.regional_doppler import ObservationArc, Region, ScoreConfig, logsumexp

TOOL_PATH = Path(__file__).parents[2] / "tools/research/refine_joint_circular_position.py"
TOOL_SPEC = importlib.util.spec_from_file_location("refine_joint_circular_position", TOOL_PATH)
TOOL = importlib.util.module_from_spec(TOOL_SPEC)
assert TOOL_SPEC.loader is not None
sys.modules[TOOL_SPEC.name] = TOOL
TOOL_SPEC.loader.exec_module(TOOL)

ORACLE_PATH = Path(__file__).with_name("joint_circular_oracle.py")
ORACLE_SPEC = importlib.util.spec_from_file_location("joint_circular_dense_oracle", ORACLE_PATH)
ORACLE = importlib.util.module_from_spec(ORACLE_SPEC)
assert ORACLE_SPEC.loader is not None
ORACLE_SPEC.loader.exec_module(ORACLE)


def shapes_from_scene(scene):
    train, test, null_train, null_test, offsets, groups = scene
    shapes = [
        TOOL.TrackShape(
            np.asarray(tr),
            np.asarray(tr) + np.asarray(te),
            TOOL.wrap_alias_hz(means),
            float(nt),
            float(nt + ne),
            np.ones(len(tr), dtype=bool),
        )
        for tr, te, nt, ne, means in zip(
            train, test, null_train, null_test, offsets, strict=True
        )
    ]
    return shapes, groups


def test_circular_arm_constructs_and_factor_has_unit_uniform_mean():
    arm = TOOL.CircularArm(3_000.0, 0.05, 1024)
    factor = TOOL.circular_factor(31_000.0, arm.grid_hz(), 3_000.0, 0.05)
    assert TOOL.maximum_factor(3_000.0, 0.05) > 1
    assert np.mean(factor) == pytest.approx(1.0, abs=2e-12)


def test_uniform_factor_exactly_reproduces_independent_shape_baseline():
    scene = ORACLE.synthetic_scene([0.1, -0.2])
    shapes, groups = shapes_from_scene(scene)
    actual = TOOL.score_shape_groups(shapes, groups, TOOL.CircularArm())
    expected_train = sum(
        np.logaddexp(logsumexp(shape.candidate_train_log), shape.null_train_log)
        - shape.null_train_log
        for shape in shapes
    )
    expected_test = sum(
        np.logaddexp(logsumexp(shape.candidate_joint_log), shape.null_joint_log)
        - np.logaddexp(logsumexp(shape.candidate_train_log), shape.null_train_log)
        - shape.null_joint_log
        + shape.null_train_log
        for shape in shapes
    )
    assert actual["training_score"] == pytest.approx(expected_train, abs=1e-12)
    assert actual["heldout_score"] == pytest.approx(expected_test, abs=1e-12)
    assert actual["pruning_log_error_bound"] == 0


def test_bounded_objective_matches_independent_dense_oracle():
    scene = ORACLE.synthetic_scene([0.55, -0.4])
    shapes, groups = shapes_from_scene(scene)
    arm = TOOL.CircularArm(3_000.0, 0.05, 512, pruning_log_error=1e-9)
    actual = TOOL.score_shape_groups(shapes, groups, arm)
    dense_train, dense_predictive = ORACLE.dense_group_score(*scene, size=512)
    null_train = sum(scene[2])
    null_test = sum(scene[3])
    assert actual["training_score"] == pytest.approx(dense_train - null_train, abs=2e-9)
    assert actual["heldout_score"] == pytest.approx(
        dense_predictive - null_test, abs=2e-9
    )
    assert actual["pruning_log_error_bound"] <= 1e-9


def test_joint_pruning_independently_retains_heldout_dominant_candidate():
    train = [np.log([1 - 1e-12, 1e-12])]
    test = [np.array([-100.0, 0.0])]
    null_train, null_test = [-1000.0], [0.0]
    offsets, groups = [[0.0, 0.0]], [0]
    scene = train, test, null_train, null_test, offsets, groups
    shapes, groups = shapes_from_scene(scene)
    arm = TOOL.CircularArm(3_000.0, 0.05, 512, pruning_log_error=1e-8)
    actual = TOOL.score_shape_groups(shapes, groups, arm)
    _, dense_predictive = ORACLE.dense_group_score(*scene, size=512)
    assert actual["heldout_score"] == pytest.approx(dense_predictive, abs=2e-8)
    train_info = actual["curves"][0][2]
    joint_info = actual["curves"][0][3]
    assert joint_info["retained_candidate_count"] >= train_info["retained_candidate_count"]


def test_identity_posterior_divides_track_mixture_inside_group_integral():
    arm = TOOL.CircularArm(3_000.0, 0.05, 512, pruning_log_error=1e-10)
    shape = TOOL.TrackShape(
        np.log([0.45, 0.35]),
        np.log([0.45, 0.35]),
        np.array([-20_000.0, 40_000.0]),
        float(np.log(0.2)),
        float(np.log(0.2)),
        np.ones(2, dtype=bool),
    )
    curve, info = TOOL.mixture_curve(
        shape.candidate_train_log,
        shape.null_train_log,
        shape.candidate_native_mean_hz,
        arm,
        track_log_error_budget=1e-10,
    )
    other = np.log(0.2 + 0.8 * TOOL.circular_factor(35_000.0, arm.grid_hz(), 3_000.0, 0.05))
    group_posterior = np.exp(curve + other - logsumexp(curve + other))
    baseline, circular, null = TOOL.training_identity_posterior(
        shape, info, group_posterior, arm
    )
    factor = TOOL.circular_factor(
        shape.candidate_native_mean_hz, arm.grid_hz(), 3_000.0, 0.05
    )
    normalization = 0.2 + np.sum(baseline[:, None] * factor, axis=0)
    expected = np.sum(group_posterior * baseline[:, None] * factor / normalization, axis=1)
    expected_null = np.sum(group_posterior * 0.2 / normalization)
    np.testing.assert_allclose(circular, expected, rtol=0, atol=2e-12)
    assert null == pytest.approx(expected_null, abs=2e-12)
    assert np.sum(circular) + null == pytest.approx(1.0, abs=2e-12)


def test_synthetic_joint_objective_recovers_injected_position():
    arm = TOOL.CircularArm(3_000.0, 0.05, 512, pruning_log_error=1e-9)

    def objective(point):
        shapes, groups = shapes_from_scene(ORACLE.synthetic_scene(point))
        return TOOL.score_shape_groups(shapes, groups, arm)["training_score"]

    fit = TOOL.refine_local_mode(
        objective,
        [1.2, 0.5],
        Region(0, 0, 20, 20),
        radius_km=5,
        max_evaluations=300,
    )
    assert fit["converged"]
    assert not fit["bound_hit"]
    np.testing.assert_allclose([fit["east_km"], fit["north_km"]], [0.4, -0.7], atol=0.01)


def test_track_shape_never_recenters_heldout_and_keeps_full_catalogue_prior():
    region = Region(0, 0, 20, 20)
    receiver = region.points([0], [0])
    arc = ObservationArc(
        np.arange(5.0),
        np.array([0.0, 0.0, 10.0, 10.0, 10.0]),
        np.zeros(5, dtype=int),
        np.array([True, True, False, False, False]),
        partition="randomized",
    )
    positions = np.tile(receiver.ecef_km[0] + receiver.up[0] * 500, (1, 5, 1))
    track = TOOL.CachedTrack(
        "session",
        "episode",
        "episode",
        0,
        "lower",
        1,
        TOOL.CANONICAL_RF_HZ,
        arc,
        positions,
        np.zeros_like(positions),
        np.array([123]),
        100,
    )
    config = ScoreConfig()
    shape = TOOL.track_shape(track, receiver, config)
    expected_train = -config.effective_count * np.log(config.signal_sigma_hz) + np.log(
        config.signal_prior / 100
    )
    expected_test = (
        -0.5 * config.effective_count * 100 / config.signal_sigma_hz**2
        - config.effective_count * np.log(config.signal_sigma_hz)
    )
    assert shape.candidate_train_log[0] == pytest.approx(expected_train)
    assert shape.candidate_joint_log[0] - shape.candidate_train_log[0] == pytest.approx(
        expected_test
    )
