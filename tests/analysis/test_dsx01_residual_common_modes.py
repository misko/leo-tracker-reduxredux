"""Overlap pairing never invents values across an RF observation gap."""

import importlib
from pathlib import Path

import numpy as np


def test_overlap_rejects_extrapolation_and_large_internal_gaps(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    pair = importlib.import_module("audit_dsx01_residual_common_modes").overlap
    a = dict(times=np.arange(0.0, 30, 0.5), residual=np.arange(60.0))
    tb = np.r_[np.arange(2.0, 8, 0.5), np.arange(18.0, 25, 0.5)]
    b = dict(times=tb, residual=tb * 2)
    t, ra, rb = pair(a, b)
    assert t.min() >= 2 and t.max() <= 24.5
    assert not np.any((t > 7.5) & (t < 18))
    np.testing.assert_allclose(rb, 2 * t)
    assert len(t) == len(ra) == len(rb)
