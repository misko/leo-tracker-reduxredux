import pytest

from tools.research.replay_stream0_pilot_replication import selected_opportunities
from tools.research.replay_stream0_pilot_replication import resolve_nominees
import json
from pathlib import Path


def test_real_receipt_nominees_resolve_to_selected_candidate_records():
    root = Path(__file__).resolve().parents[2]
    population = json.loads((root / "reports/figures/2026_09_23_independent_phase/geometry-sensitivity/stream0-raw-candidate-population.json").read_text())
    for row in population["opportunities"]:
        if row["status"] != "eligible":
            continue
        picks = resolve_nominees(row)
        for rx in ("0", "1"):
            assert [p["candidate_rank"] for p in picks[rx]] == row["nominees"][rx]
            assert all("local_epoch_sample" in p and "tracking_cfo_hz" in p for p in picks[rx])


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
