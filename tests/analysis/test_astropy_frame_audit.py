"""Research audit tests require explicit optional astropy dependency."""

from pathlib import Path

import numpy as np
import pytest


def test_orbit_errors_are_not_silently_used(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from audit_wide_astropy_frames import itrs_states

    class InvalidOrbit:
        def sgp4_array(self, jd1, jd2):
            return np.array([6]), np.zeros((1, 3)), np.zeros((1, 3))

    with pytest.raises(ValueError, match="SGP4 error"):
        itrs_states(InvalidOrbit(), np.array([1_600_000_000_000_000_000], dtype=np.int64))


def test_stationary_inertial_position_gains_earth_fixed_velocity(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from astropy.utils import iers
    from audit_wide_astropy_frames import itrs_states

    iers.conf.auto_download = False

    class FixedInertialPoint:
        def sgp4_array(self, jd1, jd2):
            return (
                np.zeros(len(jd1), int),
                np.tile([7000.0, 0, 0], (len(jd1), 1)),
                np.zeros((len(jd1), 3)),
            )

    ns = 1_600_000_000_000_000_000 + np.array([-1, 0, 1], dtype=np.int64) * 1_000_000_000
    p, v = itrs_states(FixedInertialPoint(), ns)
    np.testing.assert_allclose(np.linalg.norm(p, axis=1), 7000, atol=1e-8)
    # Transforming positions alone would leave zero velocity and fail this check.
    np.testing.assert_allclose(v[1], (p[2] - p[0]) / 2, atol=1e-6)
    assert np.linalg.norm(v[1]) == pytest.approx(0.510448, abs=1e-5)
