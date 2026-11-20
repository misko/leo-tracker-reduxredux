"""Tests for the fixed-assignment receiver oscillator and held prediction."""

from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import joint_clock_model as model
from tools.pipeline_eval.variants import robust_em as lean


def test_clock_basis_is_affine_free_and_uses_a_fixed_scan_grid():
    t = np.arange(301.0)
    origin = t - 150
    columns = model.basis(t, model.REFERENCE_HZ)
    np.testing.assert_allclose(columns.sum(axis=0), 0, atol=1e-11)
    np.testing.assert_allclose(origin @ columns, 0, atol=1e-9)
    np.testing.assert_allclose(model.basis(t[2::11], 12.4e9), columns[2::11] * (12.4 / 11.5))


def _row(lane, rf, times, values, orbit=0, alias=0):
    track = lean.Track(times, values, rf, lane, True, (times - 150.0) / 100.0, np.eye(len(times)))
    arc = lean.Arc(
        track, np.array([orbit]), values[None], np.zeros((1, len(times), 2)),
        np.zeros((1, len(times))), np.zeros(1), np.zeros(1),
    )
    return lean.Assignment(arc, 0, alias, 0.0, 2.0)


@pytest.mark.parametrize("arm", lean.ARMS)
def test_no_clock_matches_existing_regularized_fit(arm):
    t = np.linspace(0, 300, 51)
    rows = [_row(lane, 11e9 + lane * 0.2e9, t, 250 + t / 2, lane) for lane in range(4)]
    old, new = lean.fit(rows, 4, 12.5, arm), model.fit(rows, 4, 12.5, arm, clock=False)
    assert old.score == pytest.approx(new.score, abs=1e-12)
    assert old.rms_hz == pytest.approx(new.rms_hz, abs=1e-12)
    assert old.radius_km == pytest.approx(new.radius_km, abs=1e-8)
    np.testing.assert_allclose(new.state.bias, old.state.bias)
    np.testing.assert_allclose(new.state.drift, old.state.drift)
    np.testing.assert_allclose(new.state.phase, old.state.phase)
    assert new.state.c_hz_per_ghz == pytest.approx(old.state.c_hz_per_ghz)


def test_fixed_assignments_share_clock_within_receiver_and_separate_receivers():
    t = np.linspace(0, 300, 61)
    coefficients = np.zeros((2, len(model.CENTER_S)))
    coefficients[0, 3] = 180
    coefficients[1, 7] = -115
    rows = []
    for lane, rf in enumerate((10.7e9, 12.4e9, 10.7e9, 12.4e9)):
        curve = model.basis(t, rf) @ coefficients[lane // 2]
        rows.append(_row(lane, rf, t, 752.0 + 0.15 * t + curve, lane))
    old, new = lean.fit(rows, 4, 12.5, "c0"), model.fit(rows, 4, 12.5, "c0", clock=True)
    assert new.rms_hz < 0.01
    assert old.rms_hz > 25.0
    assert new.state.c_hz_per_ghz == 0.0
    _, different_band, other_receiver, _ = [model._radio(r.arc.track, new.state) for r in rows]
    np.testing.assert_allclose(different_band, rows[1].arc.track.hz, atol=0.04)
    np.testing.assert_allclose(other_receiver, rows[2].arc.track.hz, atol=0.04)


def test_held_rf_prediction_uses_frozen_clock_phase_and_period_alias(monkeypatch):
    t = np.arange(90.0, 100.0)
    coefficients = np.zeros((2, len(model.CENTER_S)))
    coefficients[0, 3] = 130
    hz = 550 + lean.PERIOD + model.basis(t, 12.4e9) @ coefficients[0]
    row = _row(1, 12.4e9, t, hz)
    state = model.ClockState(np.zeros(2), np.zeros(4), np.zeros(4), np.zeros(1), 0.0, coefficients)
    region = SimpleNamespace(site=lambda _xy: (np.zeros(3), None))

    def prediction(_tile, _orbit, times, _site, _phase, _rf):
        return (np.full(len(times), 550.0), None, None)

    monkeypatch.setattr(model.exact, "project", prediction)
    result = model.held_score([row.arc], None, region, state)
    assert result["held_score"] == pytest.approx(1.0)
    assert result["held_orbits"] == 1
    assert result["held_rf_rms_hz"] == pytest.approx(0, abs=1e-9)
    assert state.clock[0, 3] == 130


@pytest.mark.parametrize("clock", [False, True])
def test_native_adapter_changes_only_the_receiver_backend(monkeypatch, clock):
    from tools.pipeline_eval.qualification import native_clock_model_worker as adapter
    from tools.pipeline_eval.variants import robust_orbit_fit

    start_backend = robust_orbit_fit.infer
    received = []
    request = {"mode": "native"}

    def infer(observation, offer, catalogue, *, clock):
        received.append((observation, offer, catalogue, clock))
        return {"status": "ok"}

    def native_worker(packet):
        assert packet is request
        return dict(
            result=robust_orbit_fit.infer("observation", "offer", "catalogue"),
            stages=dict(
                backend_import=dict(wall_s=1, cpu_s=1),
                same_exact_backend=dict(wall_s=2, cpu_s=2),
            ),
            observation_sha256="unchanged",
        )

    monkeypatch.setattr(adapter, "setrlimit", lambda _kind, _limits: None)
    monkeypatch.setattr(adapter.native, "worker", native_worker)
    monkeypatch.setattr(model, "infer", infer)
    out = adapter.worker(request, clock=clock)
    assert received == [("observation", "offer", "catalogue", clock)]
    assert robust_orbit_fit.infer is start_backend
    assert out["observation_sha256"] == "unchanged"
    assert out["stages"]["clock_backend"] == dict(wall_s=2, cpu_s=2)
    assert out["result"]["boundary"] == adapter.BOUNDARY


def test_native_adapter_requires_the_complete_factor_boundary():
    from tools.pipeline_eval.qualification import native_clock_model_worker as adapter

    with pytest.raises(ValueError, match="only complete native factors"):
        adapter.worker({"mode": "prepared"})
