import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "clock_evaluation_test", Path(__file__).with_name("evaluate.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize("failure", ["tampered", "incomplete", "wrong_winner", "baseline_mismatch"])
def test_gate_precedes_reference_access(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    source = tmp_path / "reports/2026_09_24_local_cone_grid/inference.json"
    source.parent.mkdir(parents=True)
    points = [
        {
            "point_id": key,
            "latitude_deg": 38.0,
            "longitude_deg": -122.0,
            "methods": {"baseline": {"training_capped_loss": cost}},
        }
        for key, cost in (("a", 0.1), ("b", 0.2))
    ]
    source.write_text(json.dumps({"points": points}))
    rows = [
        {
            "point_id": p["point_id"],
            "latitude_deg": p["latitude_deg"],
            "longitude_deg": p["longitude_deg"],
            "tau_s": 0,
            "training_capped_loss": p["methods"]["baseline"]["training_capped_loss"],
            "tau0_training_capped_loss": p["methods"]["baseline"]["training_capped_loss"],
        }
        for p in points
    ]
    if failure == "baseline_mismatch":
        rows[0]["tau0_training_capped_loss"] += 0.01
    data = {
        "complete": failure != "incomplete",
        "rows": rows,
        "winner_point_id": "b" if failure == "wrong_winner" else "a",
        "bindings": {"local_grid": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()},
    }
    path, seal = tmp_path / "inference.json", tmp_path / "inference.sha256"
    path.write_text(json.dumps(data))
    seal.write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    if failure == "tampered":
        path.write_text(path.read_text() + " ")

    def forbidden():
        pytest.fail("Reference evaluator reached before inference gate")

    monkeypatch.setattr(MODULE, "reference_helper", forbidden)
    with pytest.raises(ValueError):
        MODULE.evaluate(path, seal, tmp_path / "output")
