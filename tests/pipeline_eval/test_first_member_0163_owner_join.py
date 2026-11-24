"""A changed CFO on a matching lane cannot masquerade as an identical factor."""

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
from first_member_0163_owner_join import compare_lane


def test_join_compares_the_typed_factor_after_matching_the_lane():
    row = {"candidates": [{"cfo": -0.0, "epoch": 1234}]}
    assert compare_lane(row, row, json.dumps)[0] == "exact_native_factor_set"
    assert compare_lane(row, {"candidates": [{"cfo": 0.0, "epoch": 1234}]}, json.dumps)[0] == "same_lane_different_factor_set"
    assert compare_lane(row, {"candidates": []}, json.dumps)[0] == "candidate_empty"
