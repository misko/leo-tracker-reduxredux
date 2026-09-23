import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]


def subject():
    path = ROOT / "reports/2026_09_23_train_search_ambiguity/audit.py"
    spec = importlib.util.spec_from_file_location("train_search_ambiguity", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_replayed_final_beam_contains_saved_selected_minimum():
    module = subject()
    data = json.loads(
        (ROOT / "reports/2026_09_23_long_training_search_multi/results/results.json").read_text()
    )
    for view in data["views"]:
        for search in view["searches"]:
            beam = module.replay(search["trace"])[-1]["beam"]
            assert beam[0]["objective_rmse_hz"] == search["selected"]["objective_rmse_hz"]
            assert len(beam) == 3


def test_diverse_retention_keeps_separated_lower_objectives():
    module = subject()
    rows = [
        {"objective_rmse_hz": 1.0, "east_km": 0.0, "north_km": 0.0},
        {"objective_rmse_hz": 1.1, "east_km": 0.1, "north_km": 0.0},
        {"objective_rmse_hz": 1.2, "east_km": 2.0, "north_km": 0.0},
        {"objective_rmse_hz": 1.3, "east_km": 0.0, "north_km": 2.0},
    ]
    retained = module.diverse(rows, spacing=1.0)
    assert [row["objective_rmse_hz"] for row in retained] == [1.0, 1.2, 1.3]


def test_saved_audit_marks_unexecuted_fine_levels():
    data = json.loads((ROOT / "reports/2026_09_23_train_search_ambiguity/results.json").read_text())
    first_one = [
        row for row in data["arms"] if row["group"] == "first_train" and row["scan_count"] == 1
    ]
    assert all(row["new_evaluation_count_by_level"]["0.1953125"] == 0 for row in first_one)
    refined = [row for row in data["arms"] if row["scan_count"] in (6, 16)]
    assert all(row["new_evaluation_count_by_level"]["0.1953125"] > 0 for row in refined)
