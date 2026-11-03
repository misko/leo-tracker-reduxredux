"""The persisted model receiver convention is zero-based; metadata is one-based."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "identity_audit_v2", Path(__file__).with_name("audit_v2.py")
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_receiver_conventions_match_explicitly_and_reject_wrong_conversion():
    metadata = [
        dict(observation_id=str(i), time_s=float(i), receiver=i + 1, channel=4, actual_rf_hz=11e9)
        for i in range(2)
    ]
    state = dict(
        associated=np.array([True, True]),
        satellite_number=np.array([10, 20]),
        times_s=np.array([0.0, 1.0]),
        receiver=np.array([0, 1]),
        observation_id=np.array(["0", "1"]),
        channel=np.array([4, 4]),
    )
    checks = audit.validate_alignment(state, metadata)
    assert "exact ordered receiver" in checks
    state["receiver"] += 1
    with pytest.raises(AssertionError):
        audit.validate_alignment(state, metadata)


def test_v2_preserves_non_receiver_guard():
    metadata = [dict(observation_id="x", time_s=0.0, receiver=1, channel=4, actual_rf_hz=11e9)]
    state = dict(
        associated=np.array([True]),
        satellite_number=np.array([10]),
        times_s=np.array([0.0]),
        receiver=np.array([0]),
        observation_id=np.array(["wrong"]),
    )
    with pytest.raises(AssertionError):
        audit.validate_alignment(state, metadata)
