"""Cancellation, simultaneous joins and candidate-axis integrity checks."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('differential',HERE/'run.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_arbitrary_common_receiver_drift_cancels():
    rng=np.random.default_rng(17)
    measured=rng.normal(size=(2,7))*1000
    left=rng.normal(size=(3,2,7))*1000;right=rng.normal(size=(4,2,7))*1000
    drift=20000*np.sin(np.arange(7))+.4*np.arange(7)**3
    first=module.difference_residual(measured,left,right)
    second=module.difference_residual(measured+drift[None,:],left,right)
    np.testing.assert_allclose(first,second,atol=1e-10)
    # Source-specific changes are not incorrectly erased.
    changed=measured.copy();changed[1]+=37
    np.testing.assert_allclose(module.difference_residual(changed,left,right),first+37,atol=1e-10)


def test_cartesian_candidate_order_and_difference_sign():
    measured=np.array([[1.,2.,3.],[7.,8.,9.]])
    left=np.arange(12.).reshape(2,2,3);right=np.arange(18.).reshape(3,2,3)+50
    result=module.difference_residual(measured,left,right)
    assert result.shape==(2,6,3)
    for time in range(2):
        for a in range(2):
            for b in range(3):
                np.testing.assert_array_equal(result[time,a*3+b],measured[1]-measured[0]-(right[b,time]-left[a,time]))


def track(visits,times,mask):
    return dict(receiver_id=0,rf_hz=11e9,channel=2,visits=visits,times_s=times,training_mask=mask,measured_hz=list(range(len(visits))))


def test_join_rejects_non_simultaneous_or_mixed_partition_observations():
    a=track([1,2,3],[.1,.2,.3],[True,False,True]);b=track([2,3,4],[.2,.3,.4],[False,True,False])
    joined=module.paired_observations(a,b)
    assert joined['visits']==[2,3]
    with pytest.raises(AssertionError):module.paired_observations(a,dict(b,times_s=[.21,.3,.4]))
    with pytest.raises(AssertionError):module.paired_observations(a,dict(b,training_mask=[True,True,False]))
    with pytest.raises(AssertionError):module.paired_observations(a,dict(b,rf_hz=12e9))


def test_centroid_gap_retains_true_drift_difference():
    a=track([1,2],[.1,.2],[True,False]);b=track([1,2],[.1008,.1995],[True,False])
    joined=module.paired_observations(a,b)
    np.testing.assert_array_equal(joined['source_times'],np.array([a['times_s'],b['times_s']]))
    rate=1000.
    measured=rate*joined['source_times']+12345.
    prediction=np.zeros((1,1,2))
    result=module.difference_residual(measured,prediction,prediction)
    np.testing.assert_allclose(result[0,0],rate*(joined['source_times'][1]-joined['source_times'][0]),atol=1e-10)


def test_saved_banks_keep_same_phase_target_and_candidate_support():
    result=json.loads((HERE/'results.json').read_text())
    for scan in result['scans']:
        banks=json.loads((HERE/(scan['session_id']+'-banks.json')).read_text())
        for group,a,b in zip(scan['groups'],banks['absolute'],banks['differential']):
            for field in ['y','mask','geometry']:np.testing.assert_array_equal(a[field],b[field])
            assert np.array(a['cfo_train']).shape==np.array(b['cfo_train']).shape==(41,group['candidate_pairs'])
            assert group['candidate_pairs']==len(group['candidates'][0])*len(group['candidates'][1])
            residual=np.array(group['seed_residual_hz']);mask=np.array(group['training_mask'])
            np.testing.assert_allclose(module.uncertainty.estimate_scale(residual[mask]),group['differential_scale_hz'])
