from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from leo.analysis.starlink.pilot_methods import PilotMethod
from leo.analysis.starlink.trajectories import PolynomialTrajectory, TrajectoryObservation

_PATH = Path("tools/report_full_capture_support_extension.py")
_SPEC = importlib.util.spec_from_file_location("full_capture_support_extension_tool", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _observation(index: int, time_s: float, cfo_hz: float) -> TrajectoryObservation:
    return TrajectoryObservation(
        observation_id=f"o{index}",
        method=PilotMethod.GLRT64,
        sample_start=index * 25_000,
        time_s=time_s,
        tracking_cfo_hz=cfo_hz,
        score=0.5,
        control_score=0.05,
        margin=0.45,
    )


def _trajectory(
    trajectory_id: str,
    observation_ids: tuple[str, ...],
    *,
    start_s: float,
    end_s: float,
) -> PolynomialTrajectory:
    return PolynomialTrajectory(
        trajectory_id=trajectory_id,
        method=PilotMethod.GLRT64,
        polynomial_degree=1,
        reference_time_s=0.0,
        coefficients_hz=(-1_000.0, 5_000.0),
        start_s=start_s,
        end_s=end_s,
        observation_ids=observation_ids,
        point_count=len(observation_ids),
        residual_rms_hz=0.0,
        bic=0.0,
        high_gate=0.0,
        em_iterations=0,
    )


def test_connected_support_closure_extends_only_the_seed_connected_run() -> None:
    observations = tuple(
        _observation(index, time_s, 5_000.0 - 1_000.0 * time_s)
        for index, time_s in enumerate(
            (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 10.0)
        )
    )
    seed = _trajectory(
        "seed",
        tuple(item.observation_id for item in observations if 1.0 <= item.time_s <= 2.0),
        start_s=1.0,
        end_s=2.0,
    )

    closed = _MODULE.close_degree_one_support(
        label="H1",
        family_id="family",
        seed=seed,
        observations=observations,
        alias_spacing_hz=227_272.72727272726,
        residual_gate_hz=100.0,
        maximum_gap_s=0.30,
        minimum_extension_support=2,
    )

    assert closed.trajectory.polynomial_degree == 1
    assert closed.trajectory.start_s == 0.0
    assert closed.trajectory.end_s == 2.5
    assert closed.trajectory.point_count == 11
    assert closed.trajectory.coefficients_hz[0] == pytest.approx(-1_000.0)
    assert "o11" not in closed.trajectory.observation_ids


def test_connected_support_accepts_a_short_dense_endpoint_tail() -> None:
    times = (0.0, 0.25, 0.5, 0.75, 1.0, 1.01, 1.02, 1.03)
    observations = tuple(
        _observation(index, time_s, 5_000.0 - 1_000.0 * time_s)
        for index, time_s in enumerate(times)
    )
    seed = _trajectory(
        "seed",
        tuple(item.observation_id for item in observations if item.time_s <= 0.75),
        start_s=0.0,
        end_s=0.75,
    )

    closed = _MODULE.close_degree_one_support(
        label="H1",
        family_id="family",
        seed=seed,
        observations=observations,
        alias_spacing_hz=227_272.72727272726,
        residual_gate_hz=100.0,
        maximum_gap_s=0.30,
        minimum_extension_support=4,
    )

    assert closed.trajectory.end_s == 1.03
    assert closed.added_right_count == 4


def test_support_overlap_groups_transitively_without_merging_disjoint_tracks() -> None:
    def closed(label: str, ids: tuple[str, ...]) -> object:
        trajectory = _trajectory(label, ids, start_s=0.0, end_s=1.0)
        return _MODULE.ClosedSupport(label, "family", trajectory, trajectory, 1, 0, 0, 0)

    first = closed("H1", ("a", "b", "c", "d"))
    second = closed("H2", ("a", "b", "c", "e"))
    third = closed("H3", ("x", "y", "z"))

    groups = _MODULE.overlap_groups((first, second, third), minimum_jaccard=0.60)

    assert tuple(tuple(item.label for item in group) for group in groups) == (
        ("H1", "H2"),
        ("H3",),
    )
