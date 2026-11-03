import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.localization_fast import fit_localization_fast
from leo.analysis.localization_windows import (
    WindowTrackPort, independent_scan_columns, independent_scan_precision,
)


class LinearPort:
    candidate_count = 1
    priors_piecewise_constant = True

    def __init__(self, name, clock=0., time_origin=0.):
        self.observation_ids = tuple(name+str(i) for i in range(4))
        self.matrix = np.zeros((4,6))
        self.matrix[:,:3] = [[1,0,1], [0,1,1], [1,1,-1], [2,-1,1]]
        self.time_origin = time_origin
        self.observation = self.matrix @ np.array([2.,-3.,clock,0,0,0])+time_origin

    def predict_selected(self, state, index):
        assert index == 0
        return Prediction(self.matrix@state+self.time_origin, self.matrix, np.eye(4), True)

    def score_selected(self, state, index):
        if index == 1: return -1e6
        residual = self.observation-self.predict_selected(state,index).mean
        return float(-.5*residual@residual)

    def score_all(self,state):
        return np.array([self.score_selected(state,0),-1e6])


def solve(ports, precision):
    return fit_localization_fast(np.zeros(len(precision)),ports,precision,
                                 lambda x: np.linalg.norm(x[:2])<250,max_iterations=32)


def test_one_scan_exact_solver_parity():
    local = LinearPort('one',clock=1.7,time_origin=420.)
    precision = independent_scan_precision([1])
    columns = independent_scan_columns([1])[0]
    direct = solve([local],precision)
    lifted = solve([WindowTrackPort(local,columns,6)],precision)
    assert direct.converged and lifted.converged
    np.testing.assert_array_equal(direct.mean,lifted.mean)
    assert direct.objectives == lifted.objectives


def test_joint_fit_conflicting_clocks_and_different_time_origins():
    local = [LinearPort('first',3.,0.),LinearPort('second',-3.,1270.)]
    columns = independent_scan_columns([1,1])
    precision = independent_scan_precision([1,1])
    ports = [WindowTrackPort(p,c,len(precision)) for p,c in zip(local,columns)]
    fit = solve(ports,precision)
    # Compare the full nonlinear solver result to the independent closed-form
    # Gaussian least-squares solution, including both clock prior penalties.
    matrix = np.vstack([p.predict_selected(np.zeros(10),0).jacobian for p in ports])
    target = np.concatenate([p.observation-p.local.time_origin for p in ports])
    expected = np.linalg.lstsq(matrix.T@matrix+np.diag(precision),matrix.T@target,rcond=None)[0]
    assert fit.converged
    np.testing.assert_allclose(fit.mean,expected,atol=1e-8)
    assert fit.mean[columns[0][2]] > 0 and fit.mean[columns[1][2]] < 0
    swapped = solve(list(reversed(ports)),precision)
    np.testing.assert_allclose(swapped.mean,fit.mean,atol=1e-8)


def test_jacobian_and_satellite_blocks_are_independent():
    columns = independent_scan_columns([1,1])
    assert set(columns[0][2:]).isdisjoint(columns[1][2:])
    port = WindowTrackPort(LinearPort('second',time_origin=840),columns[1],10)
    state = np.arange(10,dtype=float)/10
    prediction = port.predict_selected(state,0)
    numeric = np.column_stack([(port.predict_selected(state+v,0).mean-port.predict_selected(state-v,0).mean)/2e-4
                                for v in np.eye(10)*1e-4])
    np.testing.assert_allclose(prediction.jacobian,numeric,atol=1e-8)
    np.testing.assert_array_equal(prediction.jacobian[:,columns[0][2:]],0)


def test_duplicate_physical_observations_are_rejected():
    columns = independent_scan_columns([1,1])
    ports = [WindowTrackPort(LinearPort('same'),c,10) for c in columns]
    with pytest.raises(ValueError,match='physical observations'):
        solve(ports,independent_scan_precision([1,1]))


def test_invalid_layouts():
    for counts in ([],[0],[1,-2]):
        with pytest.raises(ValueError): independent_scan_columns(counts)
    with pytest.raises(ValueError): WindowTrackPort(LinearPort('bad'),np.array([0,1,2,3,4,4]),6)
    with pytest.raises(ValueError): WindowTrackPort(LinearPort('bad'),np.arange(6),5)
