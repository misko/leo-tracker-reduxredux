import importlib.util
from pathlib import Path

import pytest


def subject():
    path = Path(__file__).parents[2] / "reports/2026_09_23_receiver_identity_mapping/reconstruct.py"
    spec = importlib.util.spec_from_file_location("receiver_mapping", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repeated_hypothesis_support_is_allowed_only_for_same_receiver():
    join = subject().join_observations
    assert join([("a", "rx-0", "lane"), ("a", "rx-0", "lane")], ["a"])["a"]["stream_id"] == "rx-0"
    with pytest.raises(ValueError, match="conflicting"):
        join([("a", "rx-0", "lane"), ("a", "rx-1", "other")], ["a"])


def test_missing_observation_is_not_silently_dropped():
    with pytest.raises(ValueError, match="missing"):
        subject().join_observations([("a", "rx-0", "lane")], ["a", "b"])
