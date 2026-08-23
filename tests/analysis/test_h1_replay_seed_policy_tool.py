from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path("tools/report_h1_replay_seed_policy.py")
_SPEC = importlib.util.spec_from_file_location("h1_replay_seed_policy_tool", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _row(before: float, current: float, transported: float) -> dict[str, float]:
    return {
        "baseline_margin": before,
        "current_margin": current,
        "transport_margin": transported,
        "baseline_exact": before + 0.04,
        "baseline_control": 0.04,
        "current_exact": current + 0.04,
        "current_control": 0.04,
        "transport_exact": transported + 0.04,
        "transport_control": 0.04,
        "baseline_residual_hz": 100.0,
        "current_seed_hz": 2.0,
        "current_residual_hz": -1.0,
        "transport_seed_hz": -100.0,
        "transport_residual_hz": 100.0,
    }


def test_conditioned_seed_policies_transport_distinct_detector_coordinates() -> None:
    current = _MODULE.conditioned_seed_hz(
        acquired_cfo_hz=350_000.0,
        tracking_cfo_hz=300_000.0,
        lifted_trajectory_hz=299_900.0,
        policy="tracking",
    )
    transported = _MODULE.conditioned_seed_hz(
        acquired_cfo_hz=350_000.0,
        tracking_cfo_hz=300_000.0,
        lifted_trajectory_hz=299_900.0,
        policy="acquired",
    )

    assert current == 100.0
    assert transported == 50_100.0
    with pytest.raises(ValueError, match="unknown"):
        _MODULE.conditioned_seed_hz(
            acquired_cfo_hz=0.0,
            tracking_cfo_hz=0.0,
            lifted_trajectory_hz=0.0,
            policy="invalid",
        )


def test_track_summary_keeps_current_and_transport_transitions_separate() -> None:
    summary = _MODULE.summarize_track(
        [_row(0.20, 0.04, 0.19), _row(0.10, 0.08, 0.11)],
        positive_margin=0.05,
    )

    assert summary["baseline_positive_count"] == 2
    assert summary["current_transitions"] == {
        "positive_to_positive": 1,
        "positive_to_negative": 1,
    }
    assert summary["transport_transitions"] == {
        "positive_to_positive": 2,
        "positive_to_negative": 0,
    }
    assert summary["transport_total_residual_median_abs_hz"] == 0.0
    assert summary["current_total_residual_median_abs_hz"] == 1.0
