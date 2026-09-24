from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
SOURCE = HERE / "joint_rate_search.py"


def module():
    spec = importlib.util.spec_from_file_location("ds1_joint_rate_test", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def support_with_known_rate(rate: float):
    runner = module()
    points = 80
    # Make the rate identifiable even after applying the deliberately
    # non-zero Normal prior used by the production surrogate.
    sensitivity = np.linspace(-900.0, 1100.0, points)
    age = np.full(points, 8.0)
    cfo = 1300.0
    measured = cfo + sensitivity * age * rate
    return runner, runner.Support(
        measured=measured,
        nominal=np.zeros(points),
        sensitivity_hz_s=sensitivity,
        age_h=age,
        source=np.full(points, "12345"),
        track=np.full(points, "session:track"),
        weights={"session:track": 10},
        associations=[],
    )


def test_rate_profile_recovers_bounded_synthetic_phase_rate():
    runner, support = support_with_known_rate(0.08)
    fit = runner.fit_rate_support(support)
    assert fit["rate_fit_rejected_by_screening_objective"] is False
    assert fit["rate_corrections_s_h"]["12345"] == pytest.approx(0.08, abs=0.002)
    assert fit["full_observation_capped_loss"] < 1e-5
    assert fit["selection_objective"] < fit["null_rate_full_observation_capped_loss"]


def test_rate_profile_enforces_bound():
    runner, support = support_with_known_rate(0.7)
    fit = runner.fit_rate_support(support)
    assert abs(fit["rate_corrections_s_h"]["12345"]) <= runner.RATE_BOUND_S_H


def test_finalist_contract_refuses_reference_fit(tmp_path: Path):
    runner = module()
    fixture = {
        "task_id": "x",
        "group_id": "20260921_00",
        "session_ids": ["scan"],
        "session_groups": {"scan": "20260921_00"},
        "prior": {"latitude_deg": 1, "longitude_deg": 2, "radius_km": 3},
        "reference_used_for_fit": True,
    }
    path = tmp_path / "bad.json"
    path.write_text(__import__("json").dumps(fixture))
    with pytest.raises(ValueError, match="reference-free"):
        runner.task_from_finalist(path)
