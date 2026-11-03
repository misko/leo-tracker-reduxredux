"""Synthetic checks; no hardware, archive, database or QNAP required."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("sky_audit", Path(__file__).with_name("analyze.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_cardinal_geometry_and_shared_zenith():
    np.testing.assert_allclose(audit.unit(90, 0), [1, 0, 0], atol=1e-14)
    np.testing.assert_allclose(audit.unit(0, 0), [0, 1, 0], atol=1e-14)
    assert audit.off_axis(270, 80, 0) == pytest.approx(0, abs=1e-6)
    assert audit.off_axis(90, 80, 0) == pytest.approx(20)
    for rx in [0, 1]:
        assert audit.off_axis(0, 90, rx) == pytest.approx(10)


def test_polarization_symmetries():
    x = np.linspace(0, 180, 73)
    np.testing.assert_allclose(audit.polarization_power(x, circular=True), .5)
    np.testing.assert_allclose(audit.polarization_power(x), audit.polarization_power(x+180), atol=1e-14)
    np.testing.assert_allclose(audit.polarization_power(x, 35), audit.polarization_power(x+25, 60), atol=1e-14)


def test_controls_are_strict_and_all_required():
    h = dict(leading_candidate_persisted_on_heldout=True, abstention_recommended=False,
             nominal_heldout_negative_log_score=5, **dict.fromkeys(audit.CONTROLS, 6))
    assert audit.tier(h) == "control_supported"
    for k in audit.CONTROLS:
        assert audit.tier({**h, k: 5}) == "heldout_only"
        assert audit.tier({**h, k: float("nan")}) == "heldout_only"
    assert audit.tier({**h, "abstention_recommended": True}) == "rejected"


def test_pose_rejects_wrong_capture_and_tampering():
    c = dict(session_id="s", manifest_sha256="raw", radio_id="radio",
             capture_start_earliest_utc_ns=2, capture_end_utc_ns=3)
    a = dict(radio_id="radio", valid_from_utc_ns=1, valid_until_utc_ns=4)
    p = {k: v for k, v in c.items() if k != "radio_id"}
    p.update(pose_authority=a, pose_authority_digest=audit.digest(audit.canonical(a)))
    p["binding_digest"] = audit.digest(audit.canonical(p))
    assert audit.validate_pose(p, c) == a
    with pytest.raises(AssertionError):
        audit.validate_pose(p, {**c, "manifest_sha256": "another"})
    with pytest.raises(AssertionError):
        audit.validate_pose({**p, "capture_end_utc_ns": 4}, c)
