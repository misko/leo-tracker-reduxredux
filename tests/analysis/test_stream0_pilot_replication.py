import pytest

from tools.research.replay_stream0_pilot_replication import selected_opportunities


def test_whole_probe_partition_preserves_abstentions():
    population = {
        "opportunities": [
            dict(
                sample_start=i * 62500,
                partition=("held" if i % 2 else "train"),
                status="eligible" if i != 4 else "timing_failure",
            )
            for i in range(10)
        ]
    }
    train = selected_opportunities(population, "train")
    held = selected_opportunities(population, "held")
    assert [i for i, _ in train] == [0, 2, 4, 6, 8]
    assert [i for i, _ in held] == [1, 3, 5, 7, 9]
    assert train[2][1]["status"] == "timing_failure"


def test_duplicate_opportunities_fail_closed():
    population = {"opportunities": [dict(sample_start=0, partition="train") for _ in range(10)]}
    with pytest.raises(ValueError, match="unique"):
        selected_opportunities(population, "train")
