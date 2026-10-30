import numpy as np
import pytest
from include_new_family_feasible import require_qualified_control
from ds23_feasible_position import feasible_fit


def test_feasible_continuation_requires_both_verified_control_arms():
    control=dict(paired_valid=True);rows=[dict(role='control',arm=a,verified=True) for a in ('c0','fitted_c')]
    require_qualified_control(control,dict(rows=rows))
    with pytest.raises(ValueError,match='both control'):require_qualified_control(control,dict(rows=rows[:1]))
    rows[1]['verified']=False
    with pytest.raises(ValueError,match='both control'):require_qualified_control(control,dict(rows=rows))
    rows[1]['verified']=True
    with pytest.raises(ValueError,match='both control'):require_qualified_control(dict(paired_valid=False),dict(rows=rows))


def test_combined_objective_cannot_cross_incumbent_gate_to_reach_its_minimum():
    objective=lambda x:(x[0]-1.)**2+(x[1]+1.)**2
    slacks=lambda x:[.5-x[0],x[0]+2.]
    result=feasible_fit(objective,slacks,[0.,0.],[-2.,-2.],[2.,2.],iterations=48)
    assert result['feasible'] and result['score']<objective(np.zeros(2))
    assert min(slacks(result['parameters']))>=0
    np.testing.assert_allclose(result['parameters'],[.5,-1.],atol=.002)
