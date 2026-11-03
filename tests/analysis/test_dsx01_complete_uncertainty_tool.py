"""All five orbital modes share one correction across every family fragment."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def test_complete_modes_preserve_three_axes_and_add_supported_eccentricity(monkeypatch):
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("prototype_dsx01_complete_uncertainty")
    finally:
        sys.path.remove(path)
    rng = np.random.default_rng(4)
    dp, dv = rng.normal(size=(2, 6, 4, 3))
    base = dict(time_s=np.arange(4.0), position_km=dp, velocity_km_s=dv)
    monkeypatch.setattr(tool, "build_modes", lambda *args: (base, {2: dict(norad=100)}))
    derivative_p = rng.normal(size=(2, 4, 3))
    derivative_v = rng.normal(size=(2, 4, 3))
    calls = []

    def basis(j):
        calls.append(j)
        return derivative_p, derivative_v

    scan = SimpleNamespace(element_basis=basis)
    bank, metadata = tool.complete_modes(scan, [2, 4], [2])
    p = bank["position_km"].reshape(2, 5, 4, 3)
    v = bank["velocity_km_s"].reshape(2, 5, 4, 3)
    np.testing.assert_allclose(p[:, :3], dp.reshape(2, 3, 4, 3))
    np.testing.assert_allclose(v[:, :3], dv.reshape(2, 3, 4, 3))
    np.testing.assert_allclose(p[0, 3:], derivative_p * 1e-4)
    np.testing.assert_allclose(v[0, 3:], derivative_v * 1e-4)
    np.testing.assert_allclose(p[1, 3:], 0)
    assert metadata[2]["eccentricity_vector_sigma"] == 1e-4
    assert calls == [2]
    assert tool.complete_modes(scan, [2, 4], [2])[0] is bank
