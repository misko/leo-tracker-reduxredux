import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from acquisition_throughput import gates
from timing_frontier import DATA, frontier, select


@pytest.mark.parametrize("size", ["4", "16"])
@pytest.mark.parametrize("cost", [0, 14, 26])
def test_frontier_is_the_slowest_rate_passing_both_gates(size, cost):
    model = json.loads((DATA / "regional-dense-budget.json").read_bytes())
    inventory = json.loads((DATA / "acquisition-throughput.json").read_bytes())["rows"]
    rows = select(inventory, model["panels"][size]["cases"])
    rate = frontier(rows, model, cost)
    fraction = cost / model["historical_installed_solve_cpu_s"]
    assert max(gates(rows, rate, fraction, startup_s=model["common_charge_s"])) == pytest.approx(0.5)
    assert max(gates(rows, rate - 0.1, fraction, startup_s=model["common_charge_s"])) > 0.5
