import numpy as np

from probe_ds23_supported_feasibility import near_feasible,all_slacks


def test_refinement_is_bounded_to_original_near_feasible_criteria():
    assert near_feasible({'c0':{'a':-.1},'fitted_c':{'a':.1}})
    assert not near_feasible({'c0':{'a':-.3},'fitted_c':{'a':.1}})
    assert not near_feasible({'c0':{'a':.1},'fitted_c':{'a':.1}})
    assert not near_feasible({'c0':{'a':-.1}})
    assert not near_feasible({'c0':{'a':np.nan},'fitted_c':{'a':.1}})


def test_phase_constraint_checks_posterior_not_clipped_reference(monkeypatch):
    import probe_ds23_supported_feasibility as p
    from types import SimpleNamespace
    monkeypatch.setattr(p,'gate_slacks',lambda *_:{'old':1.})
    model=SimpleNamespace(state=lambda _:dict(phases=np.array([0.,15.12])))
    result=all_slacks(model,np.zeros(2),[])
    assert result['phase/1']<0 and 'phase/0' not in result


def test_confirmation_accepts_equal_saved_list_and_live_array_endpoints():
    from confirm_ds23_supported_feasibility import same_inventory
    a=dict(accepted_observation_ids=['a'],endpoint=[1.,2.])
    b=dict(accepted_observation_ids=['a'],endpoint=np.array([1.,2.]))
    assert same_inventory(a,b)
    b['endpoint'][0]=3.
    assert not same_inventory(a,b)
