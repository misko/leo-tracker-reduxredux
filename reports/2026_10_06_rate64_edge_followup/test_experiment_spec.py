"""Guard the frozen scan split and actual-to-retained replay anchors."""

import json
from pathlib import Path


def test_scans_are_disjoint_and_each_split_is_rate_edge_balanced():
    spec = json.loads((Path(__file__).parent / "data" / "experiment-spec.json").read_text())
    scans = spec["scans"]
    assert len(scans) == len({scan["session_id"] for scan in scans}) == 8
    for split in ("development", "evaluation"):
        assert {(scan["rate"], scan["edge"]) for scan in scans if scan["split"] == split} == {
            (2500000, "lower"),
            (2500000, "upper"),
            (10000000, "lower"),
            (10000000, "upper"),
        }


def test_replay_anchors_have_unique_physical_sample_coordinates():
    spec = json.loads((Path(__file__).parent / "data" / "experiment-spec.json").read_text())
    anchors = []
    for scan in spec["scans"]:
        for example in scan["examples"]:
            candidate = example["candidate"]
            assert example["channel"] in (1, 4)
            assert example["receiver_id"] in (0, 1)
            counter = int(candidate["integer_device_sample_counter"])
            assert counter > 0
            anchors.append((scan["session_id"], example["receiver_id"], counter))
    assert len(anchors) == len(set(anchors)) == 62
