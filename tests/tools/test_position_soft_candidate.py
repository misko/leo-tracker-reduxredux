import importlib.util
from pathlib import Path

import pytest


def subject():
    path = Path(__file__).parents[2] / "tools/research/position_soft_candidate.py"
    spec = importlib.util.spec_from_file_location("soft_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest():
    return {
        "partitions": {
            "train": {"session_ids": ["train"]},
            "validation": {"session_ids": ["v1", "v2"], "group_ids": ["g"]},
            "test": {"session_ids": ["test"]},
        },
        "groups": [{"group_id": "g", "session_ids": ["v1", "v2"]}],
    }


def test_validation_group_cannot_silently_include_test_evidence():
    data = manifest()
    data["groups"][0]["session_ids"].append("test")
    with pytest.raises(ValueError, match="outside validation"):
        subject().validation_windows(data)


def test_partition_overlap_rejected_before_loading():
    data = manifest()
    data["partitions"]["test"]["session_ids"].append("v1")
    with pytest.raises(ValueError, match="partition overlap"):
        subject().validation_windows(data)
