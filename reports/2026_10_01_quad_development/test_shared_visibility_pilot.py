import numpy as np
import pytest
from run_shared_visibility_pilot import allowance, acceptance, audit_directions


def test_historical_cost_is_charged():
    assert allowance(41.3)==pytest.approx(48.7)
    assert allowance(91.)==0
    for bad in [-1,np.nan,np.inf]:
        with pytest.raises(ValueError): allowance(bad)


def test_failure_cannot_be_accepted():
    assert acceptance(dict(converged=True,budget=True))
    assert not acceptance(dict(converged=True,budget=False))
    assert not acceptance({})


def test_directions_fixed_and_cover_shared_and_nuisance_coordinates():
    first=audit_directions(1107); second=audit_directions(1107)
    assert len(first)==11
    assert [n for n,_ in first[:8]]==[f'coordinate_{i}' for i in [0,1,2,3,4,5,553,1106]]
    for (name,a),(other,b) in zip(first,second,strict=True):
        assert name==other and np.array_equal(a,b)
        assert np.linalg.norm(a)==pytest.approx(1.)
