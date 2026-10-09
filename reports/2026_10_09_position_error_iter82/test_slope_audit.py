import numpy as np
import pytest
from slope_audit import reweight, slope_energy


def test_extracts_only_slope_coordinates_and_preserves_physical_norm():
    fit = dict(vector=[0] * 10, clock_coefficients=[999, 30, 40, 888, 777], objective=10)
    assert slope_energy(fit) == pytest.approx(0.25)
    basis = np.linalg.svd(np.ones((1, 3)), full_matrices=True)[2][1:].T
    physical = basis @ np.array([0.3, 0.4])
    assert physical @ physical == pytest.approx(slope_energy(fit))
    assert reweight(fit, 0.25, 0.5) == pytest.approx(8.5)
    assert reweight(fit, 0.25, 0.25) == 10


def test_reweight_round_trip():
    fit = dict(vector=[0] * 10, clock_coefficients=[5, 30, 40, 6, 7], objective=10)
    changed = dict(fit, objective=reweight(fit, 0.25, 0.5))
    assert reweight(changed, 0.5, 0.25) == pytest.approx(fit["objective"])
