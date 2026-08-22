from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from leo.analysis.starlink.pilot_methods import PilotMethod
from leo.analysis.starlink.trajectories import PolynomialTrajectory


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_five_dwell_degree1_only.py"
    spec = importlib.util.spec_from_file_location("five_dwell_degree1_only_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trajectory(degree: int) -> PolynomialTrajectory:
    return PolynomialTrajectory(
        f"trajectory-d{degree}",
        PilotMethod.GLRT64,
        degree,
        1.0,
        tuple(float(value) for value in range(degree + 1)),
        0.0,
        2.0,
        ("a", "b"),
        2,
        1.0,
        2.0,
        3.0,
        1,
    )


def test_linear_only_configuration_excludes_quadratic_and_cubic() -> None:
    tool = _tool()

    config = tool.degree1_only_config()

    assert config.polynomial_degrees == (1,)


def test_linear_only_gate_rejects_nonlinear_membership() -> None:
    tool = _tool()

    tool.assert_degree1_only((_trajectory(1),))
    with pytest.raises(AssertionError, match="nonlinear radio model"):
        tool.assert_degree1_only((_trajectory(2),))


def test_v3_candidates_are_preserved_as_independent_observations() -> None:
    tool = _tool()
    score = {
        "method": "glrt64",
        "exact_score": 4.0,
        "control_score": 1.0,
        "margin": 3.0,
        "residual_cfo_hz": 25.0,
        "tracking_cfo_hz": 10_025.0,
    }
    document = {
        "schema_version": 3,
        "detections": [
            {
                "status": "complete",
                "sample_start": 100,
                "time_s": 0.5,
                "local_epoch_sample": 3,
                "acquired_cfo_hz": 10_000.0,
                "scores": [score],
                "qam_accuracy": None,
                "qam_evm": None,
                "reason": "complete",
                "source_candidate_count": 2,
                "truncated_candidate_count": 0,
                "candidates": [
                    {
                        "rank": rank,
                        "local_epoch_sample": rank,
                        "acquired_cfo_hz": 10_000.0 + rank,
                        "scores": [{**score, "tracking_cfo_hz": 10_025.0 + rank}],
                        "qam_accuracy": None,
                        "qam_evm": None,
                    }
                    for rank in (0, 1)
                ],
            }
        ],
    }

    detections = tool.pilot_detections(document)
    observations = tool.trajectory_observations(detections)

    assert len(observations) == 2
    assert len({item.observation_id for item in observations}) == 2
    assert {item.tracking_cfo_hz for item in observations} == {10_025.0, 10_026.0}
