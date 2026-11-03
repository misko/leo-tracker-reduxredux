from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from satellite_drift_localization import (DriftLikelihood, SatelliteDriftObjective,
    drift_features, SLOPE_SIGMA_HZ_S, REFERENCE_RF_HZ)
from finite_set_likelihood import prepare_finite_set_likelihood
from rf_calibration_diagnostic import CalibratedLikelihood


def toy_objective():
    rng = np.random.default_rng(90)
    obj = SatelliteDriftObjective.__new__(SatelliteDriftObjective)
    obj.size, obj.n_satellites = 8, 2
    obj.features = np.array([-.2,.1,.2,-.3,.3])[:,None]
    obj.slope_features, obj.time_centers = drift_features(
        [10.,20.,35.,50.,65.], np.ones(5)*REFERENCE_RF_HZ, [1,1,2,2,1], [1,2])
    prepared = prepare_finite_set_likelihood([20.,30.,50.,70.,90.],np.arange(5))
    obj.likelihood = DriftLikelihood(prepared,.4,obj.features,obj.slope_features)
    matrix = rng.normal(size=(5,2,8))*10.
    intercept = rng.normal(size=(5,2))*50.
    visible = np.ones((5,2),bool)
    jac = SimpleNamespace(transpose_multiply=lambda weights: matrix.reshape(-1,8).T@weights)
    def predict(v, with_jacobian=False):
        result = (intercept+matrix@v,visible)
        return (*result,jac) if with_jacobian else result
    def evaluate(v):
        pred, vis = predict(v)
        result = obj.likelihood.evaluate(pred,vis,sigma_hz=200.,return_gradient=True)
        obj.base.last = dict(likelihood=result)
        return -result['total_log_likelihood'], -jac.transpose_multiply(result['prediction_gradient'].ravel())
    obj.base = SimpleNamespace(evaluate=evaluate,predict=predict,last=None,
        vector_gradient=lambda physical,v:physical,sigma_hz=200.)
    return obj, matrix


def test_centers_are_frozen_from_owner_times_and_shared_between_receivers():
    feature,center = drift_features([0.,10.,10.,20.],[REFERENCE_RF_HZ]*4,[1,1,2,2],[1,2])
    np.testing.assert_array_equal(center,[5.,15.])
    # Equal times/RF yield equal corrections regardless of RX or owner label.
    np.testing.assert_array_equal(feature[1],feature[2])
    doubled,_ = drift_features([0.,10.,10.,20.],[2*REFERENCE_RF_HZ]*4,[1,1,2,2],[1,2])
    np.testing.assert_array_equal(doubled,feature*2)
    for owners,numbers in (([1,1],[1,2]),([1,3],[1,2]),([1,1],[1,1])):
        with pytest.raises(ValueError):drift_features([0.,1.],[REFERENCE_RF_HZ]*2,owners,numbers)


def test_zero_slopes_exactly_reproduce_calibrated_likelihood():
    obj,_ = toy_objective()
    obj.likelihood.coefficient = 50.
    old = CalibratedLikelihood(obj.likelihood.prepared,.4,obj.features)
    old.coefficients = np.array([50.])
    pred,vis = obj.base.predict(np.zeros(obj.size))
    options = dict(sigma_hz=200.,return_gradient=True)
    expected = old.evaluate(pred,vis,**options)
    actual = obj.likelihood.evaluate(pred,vis,**options)
    for key in ('total_log_likelihood','prediction_gradient','row_association_probability'):
        np.testing.assert_array_equal(actual[key],expected[key])


def test_all_objective_gradient_components_and_prior():
    obj,_ = toy_objective()
    vector = np.r_[np.linspace(-.1,.1,8),1.,-.5,60.]
    value,g = obj.evaluate(vector)
    expected_prior = .5*np.sum((vector[8:-1]/SLOPE_SIGMA_HZ_S)**2)
    assert abs(value+obj.likelihood.last_result['total_log_likelihood']-expected_prior)<1e-10
    for j in range(len(vector)):
        e = np.eye(len(vector))[j]*1e-4
        fd = (obj.evaluate(vector+e)[0]-obj.evaluate(vector-e)[0])/2e-4
        np.testing.assert_allclose(fd,g[j],atol=2e-9,rtol=1e-6)


def test_fisher_equals_dense_design_including_zero_centered_prior():
    obj,matrix = toy_objective()
    vector = np.r_[np.zeros(8),1.,-.5,60.]
    obj.evaluate(vector)
    weights = obj.likelihood.last_result['row_association_probability']/200.**2
    design = np.zeros((5,2,11))
    design[:,:,:8] = matrix
    for j in range(2):design[:,j,8+j] = obj.slope_features[:,j]
    design[:,:,-1] = obj.features
    dense = design.reshape(-1,11)
    expected = dense.T@(weights.ravel()[:,None]*dense)
    expected[8:10,8:10] += np.eye(2)/SLOPE_SIGMA_HZ_S**2
    with patch('satellite_drift_localization._fisher_system',return_value=(expected[:8,:8],None)):
        actual = obj.curvature(vector)
    np.testing.assert_allclose(actual,expected,atol=1e-12)
    np.testing.assert_allclose(actual,actual.T,atol=1e-12)
    assert np.min(np.linalg.eigvalsh(actual))>=-1e-12
