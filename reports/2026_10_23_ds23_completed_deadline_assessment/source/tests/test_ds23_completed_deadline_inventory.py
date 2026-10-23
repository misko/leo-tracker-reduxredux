import copy

from inventory_ds23_completed_deadline_candidates import matching_RF_context


def test_equal_loss_is_not_enough_to_claim_the_same_calibration_context():
    fit=dict(negative_twice_elbo=100.,active_points=30,predictive_points=10,state=dict(beta=[1.,2.],smooth=[[3.]],phases=[0.,1.]))
    old={a:copy.deepcopy(fit) for a in ['c0','fitted_c']};current=copy.deepcopy(old)
    assert matching_RF_context(old,current)
    current['fitted_c']['state']['beta'][0]+=1.
    assert not matching_RF_context(old,current)


def test_a_changed_likelihood_point_count_cannot_pass_an_identical_nuisance_check():
    fit=dict(negative_twice_elbo=100.,active_points=30,predictive_points=10,state=dict(beta=[1.],smooth=[[3.]],phases=[0.]))
    old={a:copy.deepcopy(fit) for a in ['c0','fitted_c']};current=copy.deepcopy(old)
    current['c0']['predictive_points']=11
    assert not matching_RF_context(old,current)


def test_deadline_choice_keeps_first_passing_group_and_compares_only_its_completed_candidates(monkeypatch):
    import inventory_ds23_completed_deadline_candidates as module
    monkeypatch.setattr(module,'qualification',lambda r:dict(qualified=r['ok']))
    def trial(group,score,ok=True):
        return dict(group=dict(original_index=group,rows=[group],added_points=10),paired_valid=True,mask=[True,True],
                    arms={a:dict(ok=ok,negative_twice_elbo=score) for a in ['c0','fitted_c']})
    record=dict(status='budget_exhausted',trials=[trial(0,100),trial(1,1),trial(0,90),trial(0,0,False)])
    selected,qualified=module.completed_choice(record,[True,False])
    assert selected==2 and qualified==[0,1,2]
    record['status']='complete';assert module.completed_choice(record,[True,False])==(None,[])


def test_completed_candidate_cannot_drop_original_likelihood_observations(monkeypatch):
    import inventory_ds23_completed_deadline_candidates as module
    monkeypatch.setattr(module,'qualification',lambda r:dict(qualified=True))
    record=dict(status='budget_exhausted',trials=[dict(paired_valid=True,mask=[False,True],arms={'c0':{},'fitted_c':{}})])
    assert module.completed_choice(record,[True,False])==(None,[])
