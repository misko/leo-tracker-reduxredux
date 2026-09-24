from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def module():
    path = HERE / "run.py"
    spec = importlib.util.spec_from_file_location("iteration14_run_test", path)
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_lattice_is_symmetric() -> None:
    run = module()
    rows = run.lattice({"latitude_deg": 38.0, "longitude_deg": -122.0}, 0.1)
    assert len(rows) == 9
    assert {row["east_km_from_level_origin"] for row in rows} == {-0.1, 0.0, 0.1}
    assert {row["north_km_from_level_origin"] for row in rows} == {-0.1, 0.0, 0.1}


def test_nonconverged_rows_cannot_win() -> None:
    run = module()
    row = {
        "all_converged": False,
        "balanced_exact_capped_loss": 0.0,
        "balanced_selection_objective": 0.0,
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
    }
    assert run.ranking_key(row)[0] == float("inf")


def test_inputs_are_reference_free() -> None:
    run = module()
    iteration10, iteration12 = run.validate_inputs(run.ITER10, run.ITER12)
    assert iteration10["reference_used_for_fit"] is False
    assert iteration12["reference_used_for_fit"] is False
    assert len(run.reused_rows(iteration12)) == 9
    assert run.MAX_FULL_EDGE_STEPS == 8
    assert run.MAX_HALF_EDGE_STEPS == 4


def test_association_comparison_counts_candidate_changes() -> None:
    path = HERE / "dynamic_replay.py"
    spec = importlib.util.spec_from_file_location("iteration14_dynamic_test", path)
    assert spec is not None and spec.loader is not None
    replay = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = replay
    spec.loader.exec_module(replay)
    fixed = [
        {"session_id": "s", "track_id": "a", "candidate_id": "1"},
        {"session_id": "s", "track_id": "b", "candidate_id": "2"},
    ]
    dynamic = [
        {"session_id": "s", "track_id": "a", "candidate_id": "1"},
        {"session_id": "s", "track_id": "b", "candidate_id": "3"},
    ]
    result = replay.compare_associations(fixed, dynamic)
    assert result["identical_candidate_tracks"] == 1
    assert result["changed_candidate_tracks"] == 1
