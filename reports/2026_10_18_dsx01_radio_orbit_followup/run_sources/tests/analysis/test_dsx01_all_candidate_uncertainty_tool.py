"""Causal orbit covariance cannot vanish merely because a candidate is singleton."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_all_candidate_uncertainty")
    finally:
        sys.path.pop(0)


def test_singleton_gets_nonzero_covariance_without_changing_the_causal_scale(tool, monkeypatch):
    p = SimpleNamespace(scan=None, labels=[2, 8], supported=[2])

    def bank(scan, labels, supported, kind):
        assert supported == [2, 8]
        # Same independently supplied causal error size for either candidate.
        return np.eye(2) * 100, {j: {"sigma": 100} for j in supported}

    monkeypatch.setattr(tool, "build_modes", bank)
    assert tool.expand_uncertainty(p) is p
    assert p.single_owner_uncertainty_labels == (8,)
    assert p.supported_local == [0, 1]
    y = np.array([100.0, 100.0])
    oracle = importlib.import_module("dsx01_joint_marginal").integrated_gaussian
    old = oracle(y, np.array([[100.0], [0.0]]), 100)
    expanded = oracle(y, p.mode_bank, 100)
    np.testing.assert_allclose(old["conditional_residual_hz"], [50, 100])
    np.testing.assert_allclose(expanded["conditional_residual_hz"], [50, 50])


def test_unregistered_uncertainty_configuration_is_rejected(tool):
    with pytest.raises(ValueError, match="unknown"):
        tool.all_candidate_problem(None, None, False, variant="GPS_selected")
