import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from cumulative_graph_budget import budget


def test_projected_gates_respect_the_dense_cpu_floor_and_paired_denominators():
    result = budget()
    assert result["dense_solve_cpu_s"] == pytest.approx(22.756, abs=0.001)
    for size, saving in (("4", 3.49), ("16", 0.81)):
        panel = result["panels"][size]
        assert (
            result["dense_CPU_only_MB_s"]
            < panel["effective_MB_s_required"]
            < result["warm_weak_MB_s"]
        )
        assert max(panel["ratios_at_observed_warm_weak_rate"]) < 0.5
        assert max(panel["ratios_at_dense_cpu_only_rate"]) > 0.5
        assert panel["dense_acquire_CPU_reduction_at_zero_wait_s"] == pytest.approx(
            saving, abs=0.02
        )
