from run_dataset import overflow, additive_gate

def test_overflow_checks_early_rounds_not_only_final():
    assert overflow({'history':[{'phase_outside_reference_window':True},{'phase_outside_reference_window':False}]})
    assert not overflow({'phase_change_s':50})

def terminal(verified=True):
    return {'selected':{'arms':{a:{'owners':{'old':123}} for a in ('c0','fitted_c')}},'read_audit':{'verified':verified}}

def result(owner=123):
    return {'selected':{'arms':{a:{'owners':{'old':owner,'new':456}} for a in ('c0','fitted_c')}}}

def test_preserve_both_incumbent_owners():
    assert additive_gate(terminal(),result())[0]
    r=result();r['selected']['arms']['fitted_c']['owners']['old']=999
    assert not additive_gate(terminal(),r)[0]

def test_historical_failed_publication_guard_cannot_be_bypassed():
    assert not additive_gate(terminal(False),result())[0]

def test_no_candidate_keeps_baseline():
    assert not additive_gate(terminal(),{'selected':None})[0]
