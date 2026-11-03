import copy
from evaluate_ds23_marginal_clock import exact_original_rejection_fallback


def record():
    arms={a:dict(gates=dict(tracks=[dict(compatible=True)]),linear_gates=[],
                 endpoint_east_north_km=[0.,0.],final_phase_change_s=.036) for a in ('c0','fitted_c')}
    return dict(accepted=False,arms=arms,incumbent_arms={'saved':'unchanged'},policy_arms={'saved':'unchanged'})


def test_preexisting_phase_rejection_retains_exact_original_policy():
    assert exact_original_rejection_fallback(record())


def test_unqualified_accepted_candidate_cannot_be_hidden_by_fallback_check():
    r=record();r['accepted']=True
    assert not exact_original_rejection_fallback(r)


def test_changed_policy_is_not_an_exact_fallback():
    r=record();r['policy_arms']={'saved':'modified'}
    assert not exact_original_rejection_fallback(r)


def test_gate_passing_candidate_cannot_be_reclassified_as_original_rejection():
    r=record()
    for arm in r['arms'].values():arm['final_phase_change_s']=.001
    assert not exact_original_rejection_fallback(r)
