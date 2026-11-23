from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from physical_frontier_budget import acquisition_budget, report


def test_cpu_can_exceed_allowed_elapsed_and_reversed_clocks_fail():
    assert acquisition_budget(100, 0.75, 1.125, 200) == dict(
        target_elapsed_s=0.5, permitted_elapsed_outside_cpu_s=-0.25, required_elapsed_saving_s=0.625)
    with pytest.raises(ValueError):
        acquisition_budget(100, 0.75, 0.625, 200)


def test_two_physical_repeats_fail_both_gates_at_14_seconds_on_both_panels():
    for panel in report().values():
        arms = [a for a in panel["conditional_on_constant_rate"] if a["mode"] == "serial"]
        assert len(arms) == 2
        for arm in arms:
            assert all(g > 0.5 for g in arm["gates_at_14_s"])
            assert 0 < arm["maximum_dense_solve_s"] < 14
            assert arm["measured_prefix_rate_MB_s"] < panel["required_MB_s_at_14_s"]


def test_scaled_14_second_gate_matches_throughput_boundary_for_each_prefetch_arm():
    for panel in report().values():
        arms = [a for a in panel["conditional_on_constant_rate"] if a["mode"] == "prefetch"]
        assert len(arms) == 2
        for arm in arms:
            assert (max(arm["gates_at_14_s"]) <= 0.5) == (
                arm["measured_prefix_rate_MB_s"] >= panel["required_MB_s_at_14_s"])
