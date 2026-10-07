import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'2026_10_02_multiscan_localization'))
from finite_set_likelihood import prepare_finite_set_likelihood
from marks import SingletonMarkedLikelihood, lane_marks, mark_settings


def likelihood(mode='control'):
    odds,sigma=mark_settings(np.array([-.7,.2,.8]),mode)
    return SingletonMarkedLikelihood(np.array([50.,-140.,220.]),np.arange(3),
        np.zeros((3,1)),.1,2.,10000.,odds,sigma)


def test_neutral_reproduces_finite_set():
    obj=likelihood()
    predicted=np.array([[0.,200.],[-20.,180.],[100.,200.]])
    visible=np.array([[True,True],[False,True],[False,False]])
    actual=obj.evaluate(predicted,visible,sigma_hz=125.)
    expected=prepare_finite_set_likelihood(obj.measured,obj.group,alias_hz=10000.).evaluate(
        predicted,visible,sigma_hz=125.,detection_probability=.1,clutter_rate=2.,
        return_gradient=True,return_precision=True,implementation='batched')
    for key in ('total_log_likelihood','row_association_probability','prediction_gradient','prediction_precision'):
        np.testing.assert_allclose(actual[key],expected[key],rtol=1e-12,atol=1e-12)


@pytest.mark.parametrize('mode',['signal-prior','precision','joint','shuffled-joint'])
def test_gradient_and_normalization(mode):
    obj=likelihood(mode)
    predicted=np.array([[0.,200.],[-20.,180.],[100.,200.]])
    visible=np.ones_like(predicted,dtype=bool)
    actual=obj.evaluate(predicted,visible,sigma_hz=125.)
    for i in range(3):
        for j in range(2):
            plus=predicted.copy();minus=predicted.copy();plus[i,j]+=.001;minus[i,j]-=.001
            derivative=(obj.evaluate(plus,visible,sigma_hz=125.)['total_log_likelihood']-
                        obj.evaluate(minus,visible,sigma_hz=125.)['total_log_likelihood'])/.002
            assert derivative == pytest.approx(actual['prediction_gradient'][i,j],abs=1e-9)
    np.testing.assert_allclose(actual['row_association_probability'].sum(axis=1)+actual['clutter_probability'],1.)
    assert np.all(actual['prediction_precision']>=0)


def test_lane_ranks_ties_monotonic_transform_and_shuffle():
    margins=np.array([.1,.2,.2,.9,.5,.5])
    rx=np.array([0,0,0,0,1,1]);ch=np.zeros(6)
    marks=lane_marks(margins,rx,ch)
    assert marks[1]==marks[2] and marks[4]==marks[5]==0
    np.testing.assert_array_equal(marks,lane_marks(np.exp(margins),rx,ch))
    shuffled=lane_marks(margins,rx,ch,shuffle=True)
    np.testing.assert_array_equal(np.sort(marks[:4]),np.sort(shuffled[:4]))
    np.testing.assert_array_equal(shuffled,lane_marks(margins,rx,ch,shuffle=True))


def test_marks_invalid_and_bounded():
    with pytest.raises(ValueError): mark_settings([float('nan')],'joint')
    with pytest.raises(ValueError): mark_settings([2.],'joint')
    with pytest.raises(ValueError): mark_settings([0.],'typo')
    odds,sigma=mark_settings([-1.,0.,1.],'joint')
    np.testing.assert_allclose(odds,[.5,1.,2.]);np.testing.assert_allclose(sigma,[2**.5,1.,2**-.5])


def test_multi_candidate_windows_rejected():
    with pytest.raises(ValueError):
        SingletonMarkedLikelihood([0.,1.],[0,0],np.zeros((2,1)),.1,2.,1000.,[1,1],[1,1])


def test_association_reliability_changes_selection_without_duplicate_windows():
    from association import greedy
    times=np.arange(24,dtype=float)
    records=[dict(catalog_number=1,offset_s=0.,eligible_rows=list(range(13)),residual_hz=[0.]*13),
             dict(catalog_number=2,offset_s=0.,eligible_rows=list(range(11,24)),residual_hz=[0.]*13)]
    weights=np.r_[np.full(11,.5),np.ones(2),np.full(11,1.5)]
    control=greedy(records,np.zeros(24),np.zeros(24),times,np.ones(24))
    marked=greedy(records,np.zeros(24),np.zeros(24),times,weights)
    assert control['selected'][0]['catalog_number']==1
    assert marked['selected'][0]['catalog_number']==2
    assert len({a['row_index'] for a in marked['assignments']})==marked['assigned']
    assert all(s['reward']>10 for s in marked['selected'])
