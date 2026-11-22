import runpy
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
AUDIT = runpy.run_path(str(REPORT / "solver_fit_dependency_audit.py"))


def test_path_counts_moves_separately_from_each_round_initial_point():
    endpoint = [1., 2.]
    record = {"rounds": [
        {"detail": "accepted_optimizer_iterates", "endpoint": endpoint,
         "points": [[0., 0.], [.5, .5], endpoint]},
        {"detail": "accepted_optimizer_iterates", "endpoint": endpoint, "points": [endpoint]},
    ]}
    terminal = {"evidence": {"position_path": {"stages": [{"arms": {
        "c0": record, "fitted_c": record,
    }}]}}}
    assert AUDIT["accepted_path"](terminal) == {
        arm: {"points_by_round": [3, 1], "accepted_moves": 2} for arm in ("c0", "fitted_c")
    }
    record["rounds"][1]["detail"] = "phase_round_endpoint"
    with pytest.raises(ValueError, match="no recorded accepted-step history"):
        AUDIT["accepted_path"](terminal)


def test_profile_lookup_binds_filename_as_well_as_function():
    function = "calculate"
    key = "/frozen/history_position.py", 82, function
    rows = {key: (1, 1, 0.1, 0.1, {}), ("/stock/position.py", 43, function): None}
    assert AUDIT["lookup"](rows, "history_position.py", function) == rows[key]
    rows[("/different/history_position.py", 110, function)] = None
    with pytest.raises(ValueError, match="Expected one profiled call site"):
        AUDIT["lookup"](rows, "history_position.py", function)
