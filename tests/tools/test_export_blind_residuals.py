import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools/research/export_blind_residuals.py"
SPEC = importlib.util.spec_from_file_location("export_blind_residuals", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_residual_rows_fits_offsets_on_training_only_per_path():
    rows = [
        {"observed_hz": 11.0, "training": True, "segment": 0},
        {"observed_hz": 13.0, "training": True, "segment": 0},
        {"observed_hz": 99.0, "training": False, "segment": 0},
        {"observed_hz": -3.0, "training": True, "segment": 1},
        {"observed_hz": -1.0, "training": True, "segment": 1},
        {"observed_hz": -50.0, "training": False, "segment": 1},
    ]
    exported, offsets = MODULE.residual_rows(rows, np.array([1, 1, 1, 2, 2, 2]))
    assert offsets == {"0": 11.0, "1": -4.0}
    assert [row["predicted_hz"] for row in exported] == [12, 12, 12, -2, -2, -2]
    assert exported[2]["residual_hz"] == 87
    assert exported[5]["residual_hz"] == -48


def test_residual_rows_rejects_path_without_training_support():
    rows = [{"observed_hz": 1.0, "training": False, "segment": 0}]
    with pytest.raises(ValueError, match="training observations"):
        MODULE.residual_rows(rows, np.array([0.0]))


def test_source_rows_preserves_identifiers_and_common_partition():
    document = {
        "episodes": [{"episode_id": "e", "members": ["a"], "channel": 2}],
        "series": [
            {
                "tracklet_id": "a",
                "candidate_ids": ["o3", "o1", "o2", "o4", "o5"],
                "paired_visit_ids": ["g3", "g1", "g2", "g4", "g5"],
                "receiver_id": 1,
                "channel": 2,
                "actual_rf_hz": 10_950_000_000.0,
                "t_s": [3, 1, 2, 4, 5],
                "y_hz": [30, 10, 20, 40, 50],
            }
        ],
    }
    rows = MODULE.source_rows(document, "e")
    assert [row["observation_id"] for row in rows] == ["o1", "o2", "o3", "o4", "o5"]
    assert [row["training"] for row in rows] == [True, True, True, False, False]
    assert rows[0]["source_group_id"] == "g1"
    assert rows[0]["receiver_id"] == 1
    assert rows[0]["actual_rf_hz"] == 10_950_000_000.0
