import numpy as np
import pytest
from types import SimpleNamespace

from audit_visibility_discontinuity import normalizer
from position_structure_study import SingleWindowLikelihood


def test_irrelevant_horizon_satellite_changes_visibility_normalizer():
    data=SimpleNamespace(times=np.array([0.]),measured=np.array([0.]),group=np.array([0]),
                         numbers=np.array([10,20]),owners=np.array([10]),receiver=np.array([0]))
    obj=SingleWindowLikelihood(data,np.zeros((1,1)),'C1')
    pred=np.array([[0.,100000.]])
    a=obj.evaluate(pred,np.array([[True,False]]),sigma_hz=200.)
    b=obj.evaluate(pred,np.array([[True,True]]),sigma_hz=200.)
    logq=np.log1p(-obj.detection_probability)
    expected=normalizer(-2+logq)-normalizer(-2+2*logq)
    assert a['total_log_likelihood']-b['total_log_likelihood']==pytest.approx(expected,abs=1e-12)
    assert b['row_association_probability'][0,1]==0.
    # No frequency-gradient term can account for the jump from a boolean flag.
    np.testing.assert_array_equal(a['prediction_gradient'],b['prediction_gradient'])
