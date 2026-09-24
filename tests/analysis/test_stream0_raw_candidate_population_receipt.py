from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
RECEIPT = (
    ROOT
    / "reports/figures/2026_09_23_independent_phase/geometry-sensitivity"
    / "stream0-raw-candidate-population.json"
)


def test_stream0_population_is_randomized_before_timing_abstention() -> None:
    receipt = json.loads(RECEIPT.read_text())
    opportunities = receipt["opportunities"]

    assert receipt["schema"] == "stream0-raw-candidate-population/v1"
    assert receipt["no_iq_read"] is True
    assert len(opportunities) == 10
    assert sum(row["partition"] == "train" for row in opportunities) == 5
    assert sum(row["partition"] == "held" for row in opportunities) == 5
    assert sum(row["status"] == "eligible" for row in opportunities) == 8
    assert sum(row["status"].startswith("abstain_") for row in opportunities) == 2
    assert all("receiver_components" in row for row in opportunities)
    assert all("one_to_one_component_matchings" in row for row in opportunities)
    assert receipt["outer_random_whole_probe_split"]["assigned_before_timing_eligibility"]
    assert receipt["timeline_continuity"]["all_adjacent_device_counters_contiguous"]
    assert receipt["timeline_continuity"]["template_edge"] == "upper"
    assert receipt["timeline_continuity"]["template_edge_authority"] == "per_stream_manifest_tag"
    assert receipt["edge"] == "upper"
