import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ds789_transfer_audit import summarize  # noqa: E402


def test_gross_loss_and_training_rank_do_not_follow_held_rank():
    rows = [
        {
            "session_id": "s",
            "track_id": str(i),
            "held_count": 3,
            "training_delta": -20 if i == 0 else 0,
            "held_delta": 5 if i == 0 else (-10 if i == 1 else 0),
            "map_changed": i == 1,
            "toward_original_gradient": 1,
        }
        for i in range(10)
    ]
    result = summarize(rows)
    assert result["held_delta"] == -5
    assert result["gross_loss"] == 10 and result["gross_gain"] == 5
    assert result["training_ranked_gross_loss_share"] == 0
    assert result["held_ranked_gross_loss_share"] == 1
    assert result["same_map_held_delta"] == 5
    assert result["changed_map_held_delta"] == -10
    assert result["held_observations"] == 30


def test_ambiguous_identity_and_empty_panel_rejected():
    with pytest.raises(ValueError, match="nonempty"):
        summarize([])
    with pytest.raises(ValueError, match="duplicate"):
        summarize([{"session_id": "s", "track_id": "t"}] * 2)
