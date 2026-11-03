"""Removing a discarded Gaussian solve retains geometry and validation."""

from types import SimpleNamespace

import dsx01_joint_marginal as module
import numpy as np
import pytest


def test_geometry_only_avoids_solve_without_losing_validation(monkeypatch):
    p = SimpleNamespace(variant='fixed', sky={}, flat_times=np.arange(4.),
                        flat_labels=np.zeros(4, int), reference=np.array([.1]),
                        labels=[0], q=np.ones(4), phase_sigma=np.array([2.]),
                        mode_bank={}, supported=[], supported_local=[],
                        hardware=np.ones((4, 8)), smooth=np.ones((4, 2)),
                        constants=np.ones((4, 1)), values=np.arange(4.), sigma=150.)
    monkeypatch.setattr(module, 'paired_phase_frequency',
                        lambda bank, times, labels, ref, *xy:
                        (np.arange(4.)+ref[0]*.5, np.full(4, 45.)))
    monkeypatch.setattr(module, 'paired_frequency_modes',
                        lambda *args: np.zeros((4, 3)))
    full = module.JointMarginal.calculate(p, [0., 0.])

    def forbidden(*args):
        raise AssertionError('discarded Gaussian posterior must not be computed')

    monkeypatch.setattr(module, 'integrated_gaussian', forbidden)
    geometry = module.JointMarginal.calculate(p, [0., 0.], geometry_only=True)
    assert set(geometry) == {'features', 'elevation', 'scales', 'frequency',
                             'intercept', 'derivative'}
    for key in geometry:
        np.testing.assert_array_equal(geometry[key], full[key])
    p.sigma = -1.
    with pytest.raises(ValueError, match='positive fixed noise'):
        module.JointMarginal.calculate(p, [0., 0.], geometry_only=True)
    p.sigma = 150.
    p.values[0] = np.nan
    with pytest.raises(ValueError, match='finite inputs'):
        module.JointMarginal.calculate(p, [0., 0.], geometry_only=True)
