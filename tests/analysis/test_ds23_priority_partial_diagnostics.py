import numpy as np

from probe_ds23_point_priority_support import rank_proposals
from diagnose_ds23_partial_curved_tail import unused_blocks


def test_same_budget_prioritizes_more_native_points_over_component_name():
    small=dict(added_curved_points=18,additions=[dict(component='a')])
    large=dict(added_curved_points=56,additions=[dict(component='z')])
    middle=dict(added_curved_points=29,additions=[dict(component='b')])
    assert rank_proposals([small,middle,large])==[large,middle]


def test_a_multiple_addition_union_does_not_displace_single_proposal_budget():
    single=dict(added_curved_points=20,additions=[dict(component='z')])
    union=dict(added_curved_points=100,additions=[dict(component='a'),dict(component='b')])
    assert rank_proposals([union,single])[0] is single


def test_unused_blocks_preserve_exact_membership_without_bridging_active_points():
    t=np.arange(60,dtype=float);active=np.r_[np.ones(20,bool),np.zeros(15,bool),np.ones(10,bool),np.zeros(15,bool)]
    result=unused_blocks(t,active)
    assert len(result)==2
    np.testing.assert_array_equal(result[0],np.arange(20,35))
    np.testing.assert_array_equal(result[1],np.arange(45,60))
    assert not any(active[r].any() for r in result)


def test_extra_curve_budget_prefers_dense_whole_curves_and_keeps_partial_tracks_out():
    from probe_ds23_point_rich_extra_curve import choose_extra
    rows=[dict(curved=True,points=26,original_points=77,span_s=27.,component='partial'),
        dict(curved=True,points=36,original_points=36,span_s=44.,component='already'),
        dict(curved=True,points=47,original_points=47,span_s=34.,component='dense')]
    assert choose_extra(dict(ranking=rows),{'already'})==rows[2:]


def test_partial_prediction_uses_only_declared_unused_native_rows():
    from types import SimpleNamespace
    import pytest
    from diagnose_ds23_partial_curved_tail import data_for
    track=dict(key='partial',times=np.arange(4.),values=np.arange(4.)*100,observation_ids=['a','b','c','d'],receiver=1,channel=1)
    c=dict(features=np.ones((4,1)),noise_precision=np.ones(1),coefficient_prior_precision=np.ones(1),coefficient=np.array([.2]))
    p=SimpleNamespace(calculate=lambda x:c,noise_groups=np.zeros(4,int),keep=np.array([True,True,False,False]),point_noise=np.full(4,2.),
        hardware=np.ones((4,1)),smooth=np.zeros((4,0)),members=[0],slices=[slice(0,4)],q=np.ones(4),rows=[dict(candidate_index=7)],scan=SimpleNamespace(tracks=[track]))
    result=data_for(dict(entries=[],powers=np.ones(1)),p,np.zeros(2),0,np.array([2,3]))
    assert result['members'][0]['observation_ids']==['c','d']
    np.testing.assert_array_equal(result['values'],[200,300])
    with pytest.raises(ValueError,match='active calibration'):data_for(dict(entries=[],powers=np.ones(1)),p,np.zeros(2),0,np.array([1,2]))
