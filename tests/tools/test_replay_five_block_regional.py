import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools/research/replay_five_block_regional.py"
SPEC = importlib.util.spec_from_file_location("replay_five_block_regional", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def document(count=14):
    row = {
        "tracklet_id": "track-a",
        "t_s": list(reversed(range(count))),
        "y_hz": list(reversed(range(count))),
        "candidate_ids": [f"observation-{index}" for index in reversed(range(count))],
        "actual_rf_hz": 10.8e9,
        "channel": 1,
    }
    return {"series": [row], "episodes": [{"episode_id": "episode-a", "members": ["track-a"]}]}


def test_five_block_partition_spans_time_and_is_deterministic():
    loader = MODULE.FiveBlockLoader()
    first = loader(document(), max_per_partition=0)[0][1]
    second = MODULE.FiveBlockLoader()(document(), max_per_partition=0)[0][1]
    np.testing.assert_array_equal(first.time_s, second.time_s)
    np.testing.assert_array_equal(first.training, second.training)
    assert first.partition == "randomized"
    assert first.time_s[first.training].min() == 0
    assert first.time_s[first.training].max() == 13
    assert first.training.sum() == 8
    assert (~first.training).sum() == 6
    assert loader.documents[0]["full_observation_count"] == 14
    assert loader.documents[0]["selected_observation_count"] == 14


def test_acquisition_cap_is_applied_separately_without_changing_full_digest():
    uncapped = MODULE.FiveBlockLoader()
    capped = MODULE.FiveBlockLoader()
    uncapped(document(25), max_per_partition=0)
    arc = capped(document(25), max_per_partition=6)[0][1]
    assert arc.training.sum() == 6
    assert (~arc.training).sum() == 6
    left = uncapped.documents[0]["episodes"][0]["sources"][0]
    right = capped.documents[0]["episodes"][0]["sources"][0]
    assert left["partition_digest"] == right["partition_digest"]
    assert right["full_training"] == 15
    assert right["full_heldout"] == 10


def test_partition_rejects_short_and_duplicate_sources():
    with pytest.raises(ValueError, match="too short"):
        MODULE.FiveBlockLoader()(document(3), max_per_partition=0)
    value = document()
    value["episodes"].append({"episode_id": "duplicate", "members": ["track-a"]})
    with pytest.raises(ValueError, match="duplicate"):
        MODULE.FiveBlockLoader()(value, max_per_partition=0)


def test_completed_acquisition_gets_execution_receipt(tmp_path, monkeypatch):
    output = tmp_path / "run"
    output.mkdir()
    (output / "configuration.json").write_text("{}")
    (output / "result.json").write_text("{}")
    replay = tmp_path / "replay.py"
    replay.write_text("# replay\n")
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="abc123\n"),
    )
    MODULE.write_execution_receipt(
        SimpleNamespace(output=output), replay, {"content_digest": "sha256:partition"}
    )
    receipt = json.loads((output / "execution-receipt.json").read_text())
    assert receipt["base_git_commit"] == "abc123"
    assert receipt["partition_receipt_digest"] == "sha256:partition"
    assert receipt["position_truth_used"] is False
