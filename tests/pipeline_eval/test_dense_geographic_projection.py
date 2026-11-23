from dataclasses import replace
from hashlib import sha256
from importlib import import_module
from pathlib import Path
import subprocess

import numpy as np
import pytest


@pytest.fixture
def projector(monkeypatch, tmp_path):
    from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

    directory = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(directory))
    module = import_module("dense_geographic_projection")
    binary = tmp_path / "projection.so"
    subprocess.run(["cc", "-O3", "-shared", "-fPIC", "-fopenmp-simd", "-ffp-contract=off", "-fno-math-errno",
                    str(directory / "dense_geographic_projection.c"), "-lm", "-o", str(binary)], check=True)
    return module.Projector(binary, sha256(binary.read_bytes()).hexdigest(), phase_linear_frequency)


def geometry():
    from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry

    times = np.arange(-2., 4.)
    path = np.array([[7000., 300., -1000.], [-7600., 100., 550.]])
    velocity = np.array([[1., -5., 2.], [2., -3., -4.]])
    return prepare_phase_geometry(dict(time_s=times, position_km=path[:, None, :] + times[:, None] * velocity[:, None, :],
                                       velocity_km_s=np.broadcast_to(velocity[:, None, :], (2, 6, 3)).copy()),
                                  np.array([.0, .45, 1.3]))


def test_contiguous_projection_keeps_frequency_tangent_and_horizon(projector):
    grid = geometry()
    for latitude, longitude in ((0., 0.), (-2.5, 168.), (-60., -80.)):
        stock = projector.reference(grid, latitude, longitude, altitude_m=20., rf_hz=11.9e9)
        candidate = projector(grid, latitude, longitude, altitude_m=20., rf_hz=11.9e9)
        np.testing.assert_allclose(candidate[0], stock[0], atol=1e-7, rtol=0.)
        np.testing.assert_allclose(candidate[2], stock[2], atol=1e-7, rtol=0.)
        np.testing.assert_array_equal(candidate[1] >= 0, stock[1] >= 0)
        if latitude == 0.:
            assert (candidate[1][0] > 0).all() and (candidate[1][1] < 0).all()
    assert projector.counts["calls"] == 3
    assert projector.counts["cells"] == 18


def test_rejects_unknown_layout_and_retains_original_domain(projector):
    grid = geometry()
    noncontiguous = replace(grid, position_derivative=np.asfortranarray(grid.position_derivative))
    reference = projector.reference(grid, 0., 0.)
    candidate = projector(noncontiguous, 0., 0.)
    for old, new in zip(reference, candidate, strict=True):
        np.testing.assert_array_equal(old, new)
    assert projector.counts["original_fallback"] == 1 and not projector.counts["calls"]
    with pytest.raises(ValueError, match="domain"):
        projector(grid, 91., 0.)
