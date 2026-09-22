import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def module():
    path = (
        Path(__file__).parents[2]
        / "reports/2026_09_22_joint_blind_geometry/render_paired_comparison.py"
    )
    spec = importlib.util.spec_from_file_location("render_paired_comparison", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def document():
    value = {
        "truth_accessed": False,
        "known_position_used": False,
        "site_conditioned_candidates_used": False,
        "independent": {"latitude_deg": 0, "longitude_deg": 0},
        "paired": {"latitude_deg": 1, "longitude_deg": 1},
    }
    value["content_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return value


def test_position_tampering_is_rejected_before_truth_reveal(tmp_path):
    original = document()
    module().validate_document(original)
    original["paired"]["latitude_deg"] = 2
    source = tmp_path / "source.json"
    source.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="content seal mismatch"):
        module().evaluate([source], tmp_path / "nonexistent-reference", tmp_path / "out")
    assert not (tmp_path / "out").exists()
