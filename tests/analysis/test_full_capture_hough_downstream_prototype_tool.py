from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from leo.analysis.starlink.pilot_methods import PilotMethod
from leo.analysis.starlink.trajectories import PolynomialTrajectory, TrajectoryObservation

_PATH = Path("tools/report_full_capture_hough_downstream_prototype.py")
_SPEC = importlib.util.spec_from_file_location("hough_downstream_prototype_tool", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
tool = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = tool
_SPEC.loader.exec_module(tool)


def _row(index: int, time_s: float, *, after: float = 0.2) -> tool.ReplayProbe:
    return tool.ReplayProbe(
        label="H1",
        sample_start=index,
        time_s=time_s,
        baseline_margin=0.2,
        transported_margin=after,
        baseline_exact=0.3,
        transported_exact=0.3,
        baseline_control=0.1,
        transported_control=0.1,
        association_error_hz=10.0,
        transported_residual_hz=5.0,
    )


def _track() -> tuple[PolynomialTrajectory, tuple[TrajectoryObservation, ...]]:
    observations = tuple(
        TrajectoryObservation(
            observation_id=f"o{index}",
            method=PilotMethod.GLRT64,
            sample_start=index,
            time_s=time_s,
            tracking_cfo_hz=1_000.0 - 10.0 * time_s,
            score=0.3,
            control_score=0.1,
            margin=0.2,
        )
        for index, time_s in enumerate((0.0, 1.0, 2.0))
    )
    trajectory = PolynomialTrajectory(
        trajectory_id="seed",
        method=PilotMethod.GLRT64,
        polynomial_degree=1,
        reference_time_s=0.0,
        coefficients_hz=(-10.0, 1_000.0),
        start_s=0.0,
        end_s=2.0,
        observation_ids=tuple(item.observation_id for item in observations),
        point_count=3,
        residual_rms_hz=0.0,
        bic=0.0,
        high_gate=0.0,
        em_iterations=0,
    )
    return trajectory, observations


def test_connected_replay_runs_split_only_positive_evidence_by_gap() -> None:
    runs = tool.connected_replay_runs(
        (_row(0, 0.0), _row(1, 0.05), _row(2, 0.30), _row(3, 0.31, after=0.0)),
        threshold=0.025,
        maximum_gap_s=0.10,
    )
    assert tuple(tuple(row.sample_start for row in run) for run in runs) == ((0, 1), (2,))


def test_replay_qualified_line_preserves_no_evidence_holes() -> None:
    trajectory, observations = _track()
    refined = tool.replay_qualified_segments(
        trajectory,
        observations,
        (_row(0, 0.0), _row(1, 1.0), _row(2, 2.0)),
        threshold=0.025,
        minimum_support=3,
        alias_spacing_hz=227_272.727,
    )
    assert len(refined) == 1
    assert refined[0].start_s == 0.0
    assert refined[0].end_s == 2.0
    assert abs(refined[0].coefficients_hz[0] + 10.0) < 1e-6


def test_replay_qualified_line_rejects_harmful_conditioning() -> None:
    trajectory, observations = _track()
    refined = tool.replay_qualified_segments(
        trajectory,
        observations,
        (_row(0, 0.0), _row(1, 1.0), _row(2, 2.0, after=0.0)),
        threshold=0.025,
        minimum_support=2,
        alias_spacing_hz=227_272.727,
        maximum_negative_fraction=0.10,
    )
    assert refined == ()
