import copy
import numpy as np
from qualify_combined import ensemble,qualifies


def row(arm='c0',**changes):
    value=dict(arm=arm,hypothesis='incumbent',SD_scale=1.,objective=100000.,x=[1.,2.],
        phase_closed=True,optimizer_success=True,all_gates_pass=True,native_ids_preserved=True,
        lost_ids=[],unexpected_reassignments=[],mixture_details=[])
    return dict(value,**changes)


def test_phase_boundary_and_paired_failure_cannot_enter_ensemble():
    a=row();b=row('fitted_c',mixture_details=[dict(phase_boundary_mass=.01)])
    assert not qualifies(b)
    result=ensemble([a,b])
    assert result['paired_qualified']==0
    assert result['c0']['x'] is None and result['fitted_c']['status']=='unresolved'


def test_invalid_best_cost_never_dominates():
    rows=[row(a) for a in ('c0','fitted_c')]
    rows += [row(a,hypothesis='rival',objective=-1e8,all_gates_pass=False,x=[12.,12.]) for a in ('c0','fitted_c')]
    result=ensemble(rows)
    assert result['paired_qualified']==1
    np.testing.assert_allclose(result['c0']['x'],[1,2])


def test_error_metadata_cannot_affect_weights():
    rows=[row(a,SD_scale=s,objective=100000.+s,x=[s,2.]) for a in ('c0','fitted_c') for s in (1.,2.,4.)]
    expected=ensemble(rows);changed=copy.deepcopy(rows)
    for r in changed:r['error_m']=1e10 if r['SD_scale']==1 else 0
    assert ensemble(changed)==expected
    for arm in ('c0','fitted_c'):
        np.testing.assert_allclose(sum(r['weight'] for r in expected[arm]['models']),1,atol=1e-10)
