from pathlib import Path

import pytest


def test_export_prevents_double_counting_shared_observations(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from export_position_tracklets import validate_unique_series

    first = {"candidate_ids": ["a", "b"], "t_s": [1, 2], "y_hz": [10, 11]}
    second = {"candidate_ids": ["c", "d"], "t_s": [3, 4], "y_hz": [12, 13]}
    assert validate_unique_series([first, second]) == 4
    with pytest.raises(ValueError, match="repeated"):
        validate_unique_series([first, {**second, "candidate_ids": ["b", "c"]}])
    with pytest.raises(ValueError, match="disagree"):
        validate_unique_series([{**first, "y_hz": [10]}])
