import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools/research"))
import run_exact50_seeded_fine as runner

sys.path.pop(0)


def receipt():
    return {"complete": True, "session_id": "scan-fixture", "city": "sacramento",
            "mode": "uniform", "uniform_policy": "exact-topk", "spacing_km": 50.,
            "partition_mode": "fixed", "primary_threshold_hz": 200.,
            "radius_km": 500.,
            "top_cells": [{"east_km": float(i), "north_km": 0.} for i in range(15)]}


def test_exact_seed_input_accepts_matching_completed_search(tmp_path):
    path = tmp_path / "result.json"
    path.write_text(json.dumps(receipt()))
    seeds, _ = runner.load_exact_seeds(path, session="scan-fixture", city="sacramento")
    np.testing.assert_array_equal(seeds[:, 0], np.arange(15))


@pytest.mark.parametrize("key,value", [
    ("complete", False), ("session_id", "other"), ("city", "reno"),
    ("mode", "adaptive"), ("spacing_km", 100.), ("partition_mode", "legacy"),
    ("primary_threshold_hz", 800.), ("top_cells", []), ("radius_km", 750.),
])
def test_exact_seed_input_rejects_wrong_search_authority(tmp_path, key, value):
    data = receipt()
    data[key] = value
    path = tmp_path / "result.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        runner.load_exact_seeds(path, session="scan-fixture", city="sacramento")
