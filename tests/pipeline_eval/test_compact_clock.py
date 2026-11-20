"""Verify the compact clock's physical prior and fixed-assignment fit."""

from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import compact_clock as model
from tools.pipeline_eval.variants import robust_em as lean


def test_rate_and_acceleration_coordinates_reproduce_the_sealed_covariance():
    basis = model.basis(model.KNOTS_S, model.smooth.REFERENCE_HZ)
    np.testing.assert_allclose(basis[2], 0.0, atol=1e-12)
    slope = (basis[-1] - basis[0]) / 300
    np.testing.assert_allclose(slope, [10.0, 0, 0, 0], atol=1e-12)
    second = np.diff(basis, n=2, axis=0)
    expected = np.eye(3) + 0.25 * (np.eye(3, k=1) + np.eye(3, k=-1))
    np.testing.assert_allclose(
        second @ second.T / model.ACCELERATION_SD_HZ**2, expected, atol=1e-12,
    )


def test_continuous_clock_and_fractional_rf_scale():
    t = model.KNOTS_S[1:-1]
    low, high = model.basis(t, 10.7e9), model.basis(t, 12.6e9)
    np.testing.assert_allclose(high, low * 12.6 / 10.7, atol=1e-12)
    middle = model.basis(t + 12.0, 11.5e9)
    expected = (1 - 12 / 75) * model.basis(t, 11.5e9) + 12 / 75 * model.basis(t + 75, 11.5e9)
    np.testing.assert_allclose(middle, expected)
    np.testing.assert_allclose(
        model.basis(t - 1e-9, 11.5e9), model.basis(t + 1e-9, 11.5e9), atol=1e-7,
    )


def _row(lane, rf, t, values, orbit, alias=0):
    track = lean.Track(t, values, rf, lane, True, (t - 150.0) / 100.0, np.eye(len(t)))
    arc = lean.Arc(
        track, np.array([orbit]), values[None], np.zeros((1, len(t), 2)),
        np.zeros((1, len(t))), np.zeros(1), np.zeros(1),
    )
    return lean.Assignment(arc, 0, alias, 0.0, 2.0)


def test_fixed_rows_identify_static_mixer_clock_and_guarded_c():
    t = np.r_[np.arange(0.0, 110.0, 5.0), np.arange(130.0, 301.0, 5.0)]
    values = np.array([[0.1, 0.3, -0.6, 0.5], [-0.2, -0.3, 0.1, 0.4]])
    bias = [350.0, -220.0, 540.0, -120.0]
    slope = 235.0
    rows = []
    for lane in range(4):
        frequencies = (10.7e9, 11.3e9) if lane % 2 == 0 else (12.0e9, 12.6e9)
        for rf in frequencies:
            oscillator = model.basis(t, rf) @ values[lane // 2]
            terms = oscillator + bias[lane] + slope * (rf / 1e9 - 11.5)
            rows.append(_row(lane, rf, t, terms, lane))
    zero = model.fit(rows, 4, 12.5, "c0")
    fitted = model.fit(rows, 4, 12.5, "fitted_c")
    assert zero.state.c_hz_per_ghz == 0
    assert fitted.state.c_hz_per_ghz == pytest.approx(slope, abs=0.05)
    assert fitted.rms_hz < 0.01
    assert zero.rms_hz > 40
    np.testing.assert_allclose(fitted.state.bias, bias, atol=0.05)
    np.testing.assert_allclose(fitted.state.clock, values, atol=0.01)
    held_t = np.arange(111.0, 128.0)
    held_hz = (
        bias[2] + model.basis(held_t, 10.9e9) @ values[1] + slope * (10.9 - 11.5)
    )
    held_track = _row(2, 10.9e9, held_t, held_hz, 2).arc.track
    np.testing.assert_allclose(model._radio(held_track, fitted.state), held_hz, atol=0.05)


def test_native_worker_changes_only_the_backend(monkeypatch):
    from tools.pipeline_eval.qualification import compact_clock_worker as worker

    exact_original = model.exact.infer
    packet = {"mode": "native"}

    def native(request):
        assert request is packet
        assert model.exact.infer is model.infer
        return {
            "result": {"status": "ok"},
            "stages": {"backend_import": {"wall_s": 0, "cpu_s": 0}, "same_exact_backend": 24},
            "observation_sha256": "unchanged",
        }

    monkeypatch.setattr(worker, "setrlimit", lambda *_args: None)
    monkeypatch.setattr(worker, "native", SimpleNamespace(
        AS_LIMIT_MIB=512, worker=native, _now=lambda: None,
        _elapsed=lambda _: dict(wall_s=0.0, cpu_s=0.0),
    ))
    out = worker.worker(packet)
    assert out["observation_sha256"] == "unchanged"
    assert out["stages"]["clock_backend"] == 24
    assert model.exact.infer is exact_original
    with pytest.raises(ValueError, match="complete native"):
        worker.worker({"mode": "prepared"})
