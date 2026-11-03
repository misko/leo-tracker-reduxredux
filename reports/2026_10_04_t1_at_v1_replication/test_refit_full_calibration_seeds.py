from types import SimpleNamespace
import numpy as np
from refit_full_calibration_seeds import fixed_stationarity


def test_fixed_location_kkt_ignores_position_gradient_but_not_nuisance_gradient():
    g = np.r_[1000., -900., np.zeros(7)]
    obj = SimpleNamespace(scale=np.ones(9), bounds=[(None, None)]*9, size=8,
        base=SimpleNamespace(satellites=np.arange(2), basis=np.array([[1.], [-1.]])/np.sqrt(2),
                             minimum_shift_s=-20., maximum_shift_s=20.),
        evaluate=lambda v: (1., g.copy()))
    record = dict(vector=np.zeros(9), point_km=[0., 0.], fixed_location=True)
    assert fixed_stationarity(obj, record) == (1., 0.)
    g[3] = 2.
    assert fixed_stationarity(obj, record)[1] > 1.
