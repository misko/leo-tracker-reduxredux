from types import SimpleNamespace
import numpy as np
from visibility_step_audit import inspect_step
from finite_set_likelihood import prepare_finite_set_likelihood
from rf_calibration_diagnostic import CalibratedLikelihood


def test_visibility_audit_isolates_missed_detection_jump():
    data=SimpleNamespace(times=np.array([1.]),receiver=np.array([0]),channel=np.array([3]),
        numbers=np.array([10,20]),owners=np.array([20]),measured=np.array([0.]))
    features=np.zeros((1,1))
    likelihood=CalibratedLikelihood(prepare_finite_set_likelihood(data.measured,np.array([0])),.1,features)
    def predict(v):return np.array([[10000.,0.]]),np.array([[v[0]>=0,True]])
    base=SimpleNamespace(data=data,sigma_hz=200.,predict=predict,penalty=lambda v:(0.,np.zeros(1)))
    def evaluate(v):
        pred,vis=predict(v)
        result=likelihood.evaluate(pred,vis,sigma_hz=200.)
        return -result['total_log_likelihood'],np.zeros(2)
    obj=SimpleNamespace(size=1,scale=np.ones(2),features=features,likelihood=likelihood,base=base,evaluate=evaluate)
    result=inspect_step(obj,np.array([-1e-8,0.]),0,1e-6)
    assert result['actual_score_change']>0
    assert result['frozen_gate_score_change']==0
    assert result['visibility_jump']==result['actual_score_change']
    assert result['flips'][0]['satellite']==10
    assert result['flips'][0]['probability_after']==0
