"""Controls for sharing causal orbit hypotheses without multiplying priors."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_dsx01_pooled_position")
    finally:
        sys.path.remove(path)


class FakeFamilies:
    def __init__(self, scan, _seed, _method, _variant, _fitted_c):
        self.scan = scan
        self.coordinates = [
            (("east", 0), 1),
            (("north", 0), 1),
            (("beta", 0), 1000),
            (("phases", 0), 1),
        ]
        self.initial = np.zeros(4)
        self.lower, self.upper = np.full(4, -20), np.full(4, 20)
        self.labels, self.extra_labels = [0], []
        self.starts = dict(smooth=np.zeros((2, 0)))

    def residual(self, x):
        return np.array([x[0], x[1], x[2], x[3] / self.scan.sigma[0]])


def scans(second_line="same"):
    return [
        SimpleNamespace(
            case=f"S{i}",
            norads=np.array([100]),
            sigma=np.array([sigma]),
            elements={"100": dict(lines=["same", line])},
        )
        for i, sigma, line in ((1, 2, "same"), (2, 4, second_line))
    ]


def test_shared_full_tle_uses_one_prior_and_separate_scan_hardware(tool, monkeypatch):
    monkeypatch.setattr(tool, "FixedFamilies", FakeFamilies)
    seeds = [dict(**{"c0/shared_phase": {}})] * 2
    pool = tool.Pool(scans(), seeds, "shared_phase", "c0", "shared_tle")
    assert pool.mappings[0][:2] == pool.mappings[1][:2]
    assert pool.mappings[0][2] != pool.mappings[1][2]
    assert pool.mappings[0][3] == pool.mappings[1][3]
    x = pool.initial.copy()
    x[pool.mappings[0][3]] = 4
    # Conservative shared sigma=max(2,4): one (4/4)^2 prior, not two.
    assert pool.score(x) == pytest.approx(1)


def test_same_norad_different_tle_entries_never_share_correction(tool, monkeypatch):
    monkeypatch.setattr(tool, "FixedFamilies", FakeFamilies)
    seeds = [dict(**{"c0/shared_phase": {}})] * 2
    pool = tool.Pool(scans("newer"), seeds, "shared_phase", "c0", "shared_tle")
    assert pool.mappings[0][3] != pool.mappings[1][3]
    x = pool.initial.copy()
    x[pool.mappings[0][3]] = x[pool.mappings[1][3]] = 4
    assert pool.score(x) == pytest.approx(5)
