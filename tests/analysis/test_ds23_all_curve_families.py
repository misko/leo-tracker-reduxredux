from types import SimpleNamespace

import numpy as np
import pytest

from probe_ds23_all_curve_families import merged_prediction_data,group_candidates,choose


def test_joint_curve_prediction_preserves_cross_curve_radio_covariance_without_shared_fragment_bias():
    common=dict(p=SimpleNamespace(),coefficient=np.array([0.]),covariance=np.array([[100.]]),radio_width=1,target=0)
    def part(t,ch):
        return dict(common,times=np.array(t),values=np.zeros(len(t)),q=np.ones(len(t)),noise=np.ones(len(t))*2,
                    radio=np.ones((len(t),1)),members=[dict(receiver=1,channel=ch)])
    merged=merged_prediction_data([part([1.,2.],1),part([3.],4)])
    np.testing.assert_allclose(merged['base_covariance'],[[90104,90100,100],[90100,90104,100],[100,100,90104]])
    assert merged['held_owners']==2
    np.testing.assert_array_equal(merged['groups'],[0,0,1])
    with pytest.raises(ValueError,match='same original calibration'):
        merged_prediction_data([part([1.],1),dict(part([2.],4),coefficient=np.array([1.]))])


def test_common_second_candidate_is_kept_across_curves():
    def target(ids):
        return dict(candidates=[dict(candidate_index=j,qualified=ok) for j,ok in ids])
    groups=group_candidates([target([(1,True),(2,True),(3,False)]),target([(4,True),(2,True),(3,True)])])
    assert len(groups[2])==2 and len(groups[3])==1


def test_selection_never_prefers_a_failed_or_smaller_recovery_for_its_score():
    def trial(n,valid,loss):
        return dict(added_curved_points=n,paired_valid=valid,additions=[dict(component='same')],
                    arms={'c0':dict(corrected_selection_loss=loss)})
    a,b,c=trial(10,True,100),trial(20,False,0),trial(10,True,90)
    assert choose([a,b,c]) is c
