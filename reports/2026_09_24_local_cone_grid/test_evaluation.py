"""The reference evaluator cannot accept unsealed or misselected inference."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "local_grid_evaluation", Path(__file__).with_name("evaluate.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_fixture(tmp_path, complete=True, winner="a"):
    data = {
        "complete": complete,
        "points": [
            {
                "point_id": key,
                "latitude_deg": 38.0,
                "longitude_deg": -122.0,
                "methods": {method: {"training_capped_loss": cost} for method in MODULE.METHODS},
            }
            for key, cost in (("a", 0.1), ("b", 0.2))
        ],
        "winners": {method: {"point_id": winner} for method in MODULE.METHODS},
    }
    path = tmp_path / "inference.json"
    path.write_text(json.dumps(data))
    seal = tmp_path / "inference.sha256"
    seal.write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    return path, seal


@pytest.mark.parametrize("failure", ["tampered", "incomplete", "wrong_winner"])
def test_rejected_inference_cannot_reach_reference_evaluation(tmp_path, monkeypatch, failure):
    path, seal = write_fixture(
        tmp_path, complete=failure != "incomplete", winner="b" if failure == "wrong_winner" else "a"
    )
    if failure == "tampered":
        path.write_text(path.read_text() + " ")

    def forbidden():
        pytest.fail("Reference comparison reached before inference gate")

    monkeypatch.setattr(MODULE, "old_winners", forbidden)
    with pytest.raises(ValueError):
        MODULE.evaluate(path, seal, tmp_path / "output")


def test_complete_training_selected_inference_passes_gate(tmp_path):
    path, seal = write_fixture(tmp_path)
    data, digest = MODULE.load_sealed(path, seal)
    assert data["winners"]["baseline"]["point_id"] == "a"
    assert digest == seal.read_text()
