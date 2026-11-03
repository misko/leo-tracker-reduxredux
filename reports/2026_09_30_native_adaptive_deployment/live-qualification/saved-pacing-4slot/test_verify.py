import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("saved_pacing_verify", HERE / "verify.py")
VERIFY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VERIFY)


def test_nearest_rank_and_strict_json():
    assert VERIFY.nearest_rank([0, 10, 20, 30], 0.50) == 10
    assert VERIFY.nearest_rank([0, 10, 20, 30], 0.95) == 30
    with pytest.raises(ValueError, match="duplicate JSON key"):
        VERIFY.strict_loads('{"a": 1, "a": 2}', "test")


def test_existing_queue_four_paced_artifact():
    report = HERE.parents[1]
    result = VERIFY.verify_paced(report / "runtime/paced-with-location.jsonl")
    assert result["completed"] == 80
    assert result["rejected"] == 0
    assert result["queue_high_water"] <= 4
