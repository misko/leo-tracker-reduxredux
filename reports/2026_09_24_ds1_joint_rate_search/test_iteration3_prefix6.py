from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SOURCE = HERE / "iteration3_prefix6.py"


def module():
    spec = importlib.util.spec_from_file_location("iteration3_prefix6_test", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_tau_stencil_is_symmetric_and_bounded():
    runner = module()
    assert runner.tau_stencil(-1.25) == (-1.5, -1.25, -1.0)
    with pytest.raises(ValueError, match="cache support"):
        runner.tau_stencil(5.0)


def test_public_trace_strips_associations_and_cfo_details():
    runner = module()
    row = {
        "east_km": 1.0,
        "north_km": 2.0,
        "latitude_deg": 3.0,
        "longitude_deg": 4.0,
        "tau_s": 0.0,
        "track_associations": [{"candidate_id": "42"}],
        "fit": {
            "selection_objective": 0.1,
            "full_observation_capped_loss": 0.09,
            "null_rate_full_observation_capped_loss": 0.2,
            "prior_penalty": 0.01,
            "rate_boundary_count": 0,
            "track_cfo_hz": {"track": 999.0},
        },
    }
    public = runner._public_row(row)
    assert public["track_count"] == 1
    assert "track_cfo_hz" not in public


def test_source_contract_has_no_reference_field():
    runner = module()
    source = {
        "task_id": "task",
        "group_id": "20260921_00",
        "session_ids": ["scan"],
        "session_groups": {"scan": "20260921_00"},
        "prior": {},
    }
    task = runner._task_from_source(source)
    assert "reference" not in task
    assert task["method"] == "global_tau_per_norad_orbit_rate"
