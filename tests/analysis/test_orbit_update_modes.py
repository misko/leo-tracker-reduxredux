from pathlib import Path

import numpy as np


def test_rtn_basis_is_right_handed_and_velocity_is_consistent(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from study_orbit_update_modes import corrected_rtn, rtn_basis

    def orbit(t):
        t = np.asarray(t)
        w = 0.001
        p = np.column_stack([7000 * np.cos(w * t), 7000 * np.sin(w * t), np.zeros(len(t))])
        v = np.column_stack([-7 * np.sin(w * t), 7 * np.cos(w * t), np.zeros(len(t))])
        return p, v

    def result(t):
        p, v = orbit(t)
        q = rtn_basis(p, v)
        qd = (rtn_basis(*orbit(t + 0.01)) - rtn_basis(*orbit(t - 0.01))) / 0.02
        return corrected_rtn(
            p, v, q, qd, np.array([0.2, -3.0, 0.1]), np.array([0.001, 0.002, -0.001]), t
        )

    t = np.array([-10.0, 0.0, 15.0])
    q = rtn_basis(*orbit(t))
    np.testing.assert_allclose(
        np.einsum("nji,njk->nik", q, q), np.tile(np.eye(3), (len(t), 1, 1)), atol=1e-12
    )
    np.testing.assert_allclose(np.cross(q[:, :, 0], q[:, :, 1]), q[:, :, 2], atol=1e-12)
    derivative = (result(t + 0.001)[0] - result(t - 0.001)[0]) / 0.002
    np.testing.assert_allclose(result(t)[1], derivative, atol=1e-8)


def test_doppler_retains_actual_earth_rotation_epoch(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from study_orbit_update_modes import doppler

    p = np.array([[7000.0, 0.0, 0.0]])
    v = np.array([[0.0, 7.0, 0.0]])
    # Same inertial state but different reception epoch changes observer geometry.
    a = doppler(p, v, np.array([1789800000000000000]), np.array([6378.0, 0.0, 0.0]))
    b = doppler(p, v, np.array([1789800060000000000]), np.array([6378.0, 0.0, 0.0]))
    assert abs(a[0] - b[0]) > 1


def test_report_does_not_attribute_identity_or_site_changes_to_orbit(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from report_orbit_update_modes import explanation

    assert "Different satellite" in explanation({"identity_changed": True})
    assert "receiver/clock" in explanation({"identity_changed": False, "identical_tle": True})
    row = {
        "identity_changed": False,
        "identical_tle": False,
        "geometry": {
            "rtn_position_energy_fraction": [0.9, 0.09, 0.01],
            "models": {
                "phase1": {"orbit_doppler_energy_explained": 0.1},
                "rtn3": {"orbit_doppler_energy_explained": 0.99},
            },
        },
        "controls": [{"old_rms_hz": 60, "new_rms_hz": 80}],
    }
    text = explanation(row)
    assert "component: radial" in text
    assert "Time shift alone is inadequate" in text
    assert "does not improve measured RMS" in text
