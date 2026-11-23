import copy
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))
from regional_dense_budget import model, select


def test_roster_keeps_order_and_all_outcomes():
    rows = [{"case": "b", "stages": [0, 0, 11]}, {"case": "a", "stages": [2, 2, 2]}]
    assert select(rows, ["a", "b"]) == rows[::-1]
    for roster in (["a", "a"], ["missing"]):
        with pytest.raises(ValueError, match="unique"):
            select(rows, roster)


def test_gate_transfer_requires_same_complete_science_and_same_receiver():
    result = json.loads((HERE / "measurements/regional-dense-pair.json").read_bytes())
    predictions = model(result)["panels"]
    assert predictions["4"]["cases"] == predictions["16"]["cases"][:4]
    assert len(predictions["55"]["cases"]) == 55
    assert predictions["55"]["unchanged_outcomes"] == 3
    for key in ("same_complete_science", "packet_sha256"):
        changed = copy.deepcopy(result)
        if key == "same_complete_science":
            changed[key] = False
        else:
            changed["binding"][key] = "another detector"
        with pytest.raises(ValueError, match="Dense solve"):
            model(changed)
