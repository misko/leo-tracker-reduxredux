from copy import deepcopy

from investigate_cohort_priority_tracks import qualifies


def test_reentry_requires_both_arms_and_preserves_original_points():
    row=dict(gates={'tracks':[{'compatible':True}]},linear_gates=[{'compatible':True}],
        final_phase_change_s=.001,endpoint_east_north_km=[1.,2.],proposed_associated_ids=['old','new'])
    pair={a:deepcopy(row) for a in ('c0','fitted_c')}
    baseline={a:dict(proposed_associated_ids=['old']) for a in pair}
    assert qualifies(pair,baseline)
    pair['fitted_c']['linear_gates'][0]['compatible']=False
    assert not qualifies(pair,baseline)
    pair['fitted_c']['linear_gates'][0]['compatible']=True
    pair['c0']['proposed_associated_ids']=['new']
    assert not qualifies(pair,baseline)


def test_reentry_rejects_nonconvergence_even_if_residuals_pass():
    row=dict(gates={'tracks':[{'compatible':True}]},linear_gates=[],
        final_phase_change_s=.02,endpoint_east_north_km=[0.,0.],proposed_associated_ids=['old','new'])
    pair={a:deepcopy(row) for a in ('c0','fitted_c')}
    assert not qualifies(pair,{a:dict(proposed_associated_ids=['old']) for a in pair})
