import copy

import pytest

from tools.research.run_receiver_orbit_residual import (
    canonical_digest,
    load_episode,
    safe_child,
    verify_content_digest,
)


def candidate(norad, observation="obs"):
    return {
        "catalog_number": norad,
        "soft_weight": 0.8,
        "rows": [
            {
                "observation_id": f"{observation}-{index}",
                "utc_ns": index,
                "training": index < 2,
                "receiver_id": 0,
                "time_s": float(index),
                "residual_hz": 1.0,
                "satellite_design_hz_per_s_h": 2.0,
            }
            for index in range(4)
        ],
    }


def test_loader_rejects_misaligned_candidate_rows():
    value = {
        "episode_id": "track",
        "candidate_support": {
            "candidates": [candidate(1), candidate(2, observation="different")],
            "null_probability": 0.1,
            "omitted_probability_mass": 0.1,
        },
    }
    with pytest.raises(ValueError, match="not aligned"):
        load_episode("session", value)


def test_content_digest_detects_poisoning_and_paths_stay_basenames(tmp_path):
    document = {"truth_accessed": False, "rows": 4}
    document["content_digest"] = canonical_digest(document)
    verify_content_digest(document)
    poisoned = copy.deepcopy(document)
    poisoned["truth_accessed"] = True
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_content_digest(poisoned)
    assert safe_child(tmp_path, "scan.json") == tmp_path / "scan.json"
    with pytest.raises(ValueError, match="safe basename"):
        safe_child(tmp_path, "../scan.json")


def test_canonical_digest_survives_numeric_key_json_roundtrip():
    document = {"satellite_rates": {2: 0.02, 10: -0.01}}
    round_tripped = __import__("json").loads(__import__("json").dumps(document))
    assert canonical_digest(document) == canonical_digest(round_tripped)
