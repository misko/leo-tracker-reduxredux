# ruff: noqa: I001
"""Independent tests for parent-linear best-first priority estimates."""

from __future__ import annotations

import importlib.util
import hashlib
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "research"
sys.path.insert(0, str(TOOLS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SEARCH = load("best_first_tle_search")
PRIORITY = load("tle_parent_priority")
from leo.analysis.research.regional_doppler import Region  # noqa: E402


def bank(track_id, measured=None):
    region = Region(0.0, 0.0, 200.0, 200.0)
    site = region.points([0.0], [0.0])
    up = site.up[0]
    tangent = np.cross(up, [0.0, 0.0, 1.0])
    tangent /= np.linalg.norm(tangent)
    offsets = np.asarray([-30.0, -10.0, 10.0, 30.0])
    position = np.asarray(
        [[site.ecef_km[0] + up * 1000.0 + tangent * offset for offset in offsets]]
    )[None]
    velocity = np.broadcast_to(tangent * 7.0, position.shape).copy()
    return PRIORITY.TrackPredictionBank(
        tracklet_id=track_id,
        observation_ids=tuple(
            "sha256:" + hashlib.sha256(f"{track_id}-{index}".encode()).hexdigest()
            for index in range(4)
        ),
        measured_hz=np.zeros(4) if measured is None else np.asarray(measured, dtype=float),
        times_s=np.arange(4.0),
        span_s=3.0,
        support_digest="sha256:" + ("1" if track_id == "a" else "2") * 64,
        position_km=position,
        velocity_km_s=velocity,
        norads=np.asarray([100 if track_id == "a" else 200]),
        coarse_position_km=position[:, 0],
        coarse_node_indices=np.arange(4),
    )


def parent_row(track_id, norad):
    return SEARCH.TrackResidual(
        track_id,
        0.0,
        1.0,
        best_candidate={"norad": norad, "tau_s": 0.0},
    )


def cell(east=25.0, north=0.0, spacing=50.0):
    return SEARCH.SearchCell("child", east, north, spacing, 1, "parent", True, 0.0, "test")


def test_central_parent_jacobian_recovers_local_prediction_and_reuses_model():
    source = bank("a")
    region = Region(0.0, 0.0, 200.0, 200.0)
    priority = PRIORITY.make_parent_priority(
        (source,), region, "sha256:" + "3" * 64, {"a": 1.0}, taus=np.asarray([0.0])
    )
    centre, east_jacobian, north_jacobian, _ = priority._model(0.0, 0.0, source, 100)
    step = 0.01
    actual = PRIORITY._prediction(source, 0, region.points([step], [0.0]))

    np.testing.assert_allclose(actual, centre + east_jacobian * step, rtol=2e-4, atol=2e-4)
    assert np.linalg.norm(east_jacobian) > 0.0

    parent = SEARCH.point_evaluation(0.0, 0.0, (parent_row("a", 100),))
    priority(cell(), parent, {})
    priority(cell(25.0, 25.0), parent, {})
    metrics = priority.metrics()
    assert metrics["parent_track_models_built"] == 1
    assert metrics["parent_track_model_cache_hits"] >= 2


def test_parent_stencil_minimizes_joint_position_not_each_track_separately():
    derivative = np.asarray([[-1.0, -0.5, 0.5, 1.0]])
    source_a = bank("a", measured=25.0 * derivative[0])
    source_b = bank("b", measured=-25.0 * derivative[0])
    region = Region(0.0, 0.0, 200.0, 200.0)
    parent = SEARCH.point_evaluation(
        0.0,
        0.0,
        (parent_row("a", 100), parent_row("b", 200)),
    )

    def fixed_model(_east, _north, _bank, _norad):
        return (
            np.zeros((1, 4)),
            derivative,
            np.zeros((1, 4)),
            np.asarray([True, True, False, False]),
        )

    joint = PRIORITY.make_parent_priority(
        (source_a, source_b),
        region,
        "sha256:" + "4" * 64,
        {"a": 1.0, "b": 1.0},
        taus=np.asarray([0.0]),
    )
    joint._model = fixed_model
    one_a = PRIORITY.make_parent_priority(
        (source_a,), region, "sha256:" + "4" * 64, {"a": 1.0}, taus=np.asarray([0.0])
    )
    one_a._model = fixed_model
    one_b = PRIORITY.make_parent_priority(
        (source_b,), region, "sha256:" + "4" * 64, {"b": 1.0}, taus=np.asarray([0.0])
    )
    one_b._model = fixed_model

    target = cell(0.0, 0.0)
    joint_value = joint(target, parent, {})
    a_value = one_a(target, SEARCH.point_evaluation(0.0, 0.0, (parent_row("a", 100),)), {})
    b_value = one_b(target, SEARCH.point_evaluation(0.0, 0.0, (parent_row("b", 200),)), {})

    assert a_value == 0.0 and b_value == 0.0
    assert joint_value > 0.0


def test_exact_cache_clamps_priority_and_unexplored_parent_none_is_explicit_zero():
    source = bank("a")
    region = Region(0.0, 0.0, 200.0, 200.0)
    priority = PRIORITY.make_parent_priority(
        (source,), region, "sha256:" + "5" * 64, {"a": 1.0}, taus=np.asarray([0.0])
    )
    target = cell()
    exact = SEARCH.point_evaluation(target.east_km, target.north_km, (parent_row("a", 100),))
    parent = SEARCH.point_evaluation(0.0, 0.0, (parent_row("a", 100),))

    assert priority(target, parent, {(target.east_km, target.north_km): exact}) == 0.0
    assert priority(target, None, {}) == 0.0
    assert (
        priority(target, None, {(target.east_km, target.north_km): exact}) == exact.weighted_mse_hz2
    )
    assert priority.metrics()["priority_is_certified_bound"] is False
