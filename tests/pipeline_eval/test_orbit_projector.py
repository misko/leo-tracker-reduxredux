from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research import phase_linear_geometry as original
from tools.pipeline_eval.qualification import projector_audit
from tools.pipeline_eval.variants import orbit_projector as compact


@pytest.fixture(scope="module")
def projector(tmp_path_factory):
    lib = tmp_path_factory.mktemp("compact-orbit") / "project.so"
    compact.compile_kernel(lib)
    return compact.Projector(lib)


@pytest.fixture
def bank():
    rng = np.random.default_rng(22617)
    t = np.array([-10.0, -5.0, -1.0, 2.0, 4.0, 8.0, 14.0])
    p = rng.normal(size=(4, 1, 3))
    p = 7000 * p / np.linalg.norm(p, axis=-1, keepdims=True)
    v = rng.normal(size=(4, 1, 3)) + rng.normal(0, 0.5, (4, len(t), 3))
    return dict(time_s=t, position_km=p + t[None, :, None] * v, velocity_km_s=v)


@pytest.mark.parametrize("phase", [0.0, 1.25, np.array([0, -0.4, 1.15, 1.0])])
def test_compact_projection_matches_reference_across_phase_knots_and_locations(
    projector, bank, phase
):
    t = np.array([-0.95, 2.0, 2.02, 7.1, 2.02])
    old = original.prepare_phase_geometry(bank, t, phase)
    new = compact.prepare(bank, t, phase)
    bank["position_km"][:] = 0
    for lat, lon in [(0.0, 0.0), (89.3, -179.99), (-55.0, 170.0)]:
        a = original.phase_linear_frequency(old, lat, lon, rf_hz=10.9e9, altitude_m=550.0)
        b = projector.evaluate(new, lat, lon, rf_hz=10.9e9, altitude_m=550.0)
        for x, y, limit in zip(a, b, [1e-5, 1e-8, 1e-5], strict=True):
            np.testing.assert_allclose(x, y, atol=limit, rtol=0)


def test_approaching_and_receding_satellites_have_opposite_doppler(projector):
    positions = np.zeros((2, 3, 3))
    positions[:, :, 0] = [[6999, 7000, 7001], [7001, 7000, 6999]]
    velocities = np.zeros_like(positions)
    velocities[:, :, 0] = [[0.75, 1.0, 1.25], [-0.75, -1.0, -1.25]]
    bank = dict(time_s=[-1, 0, 1], position_km=positions, velocity_km_s=velocities)
    stencil = compact.prepare(bank, [0.0])

    frequency, elevation, derivative = projector.evaluate(stencil, 0.0, 0.0, rf_hz=299_792_458)

    np.testing.assert_allclose(frequency[:, 0], [-1000, 1000], rtol=0, atol=1e-10)
    np.testing.assert_allclose(elevation[:, 0], [90, 90], rtol=0, atol=1e-10)
    np.testing.assert_allclose(derivative[:, 0], [-250, 250], rtol=0, atol=1e-8)


def test_empty_grids_support_checks_and_native_bounds(projector, bank):
    for partial in (bank, {k: (v[:0] if k != "time_s" else v) for k, v in bank.items()}):
        stencil = compact.prepare(partial, np.empty(0))
        expected_shape = (len(partial["position_km"]), 0)
        assert all(a.shape == expected_shape for a in projector.evaluate(stencil, 45.0, 20.0))
    with pytest.raises(ValueError, match="extrapolates"):
        compact.prepare(bank, [-10.0])
    with pytest.raises(ValueError, match="per satellite"):
        compact.prepare(bank, [0.0], [-1.0, 2.0])
    st = compact.prepare(bank, [0.0])
    with pytest.raises(ValueError, match="stencil"):
        projector.evaluate(replace(st, fraction=st.fraction[:0]), 0.0, 0.0)
    with pytest.raises(ValueError, match="index"):
        projector.evaluate(replace(st, index=np.full_like(st.index, 5000)), 0.0, 0.0)
    for lat, lon in ((90.01, 0), (0, 180.01)):
        with pytest.raises(ValueError, match="geodetic"):
            projector.evaluate(st, lat, lon)


def test_transfer_evidence_requires_bound_projection_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(projector_audit.v5_lean, "SOURCE", tmp_path / "different-source")
    out = tmp_path / "transfer.json.gz"

    with pytest.raises(ValueError, match="requires the frozen v5 projection source"):
        projector_audit.transfer(out, 1)
    assert not out.exists()
