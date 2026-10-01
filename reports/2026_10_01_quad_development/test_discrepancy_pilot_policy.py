import numpy as np
import pytest
from run_discrepancy_pilot import remaining_budget
from discrepancy_window_inputs import initial_state


@pytest.mark.parametrize('size',[1,2,4])
def test_charged_budget_boundary(size):
    assert remaining_budget(90*size-10,size)==10
    with pytest.raises(ValueError):remaining_budget(90*size-9.99,size)


def test_invalid_budget():
    for seconds,size in ((-1,1),(np.nan,2),(0,3),(np.inf,4)):
        with pytest.raises(ValueError):remaining_budget(seconds,size)


def test_initial_state_preserves_original_and_adds_only_zero_offsets():
    parent=dict(best=dict(mean=[1.,2.,3.,4.]),binding=dict(size=4))
    base=initial_state(parent,'baseline');aug=initial_state(parent,'sigma1')
    np.testing.assert_array_equal(aug,np.r_[base,np.zeros(8)])
    base[0]=99
    assert parent['best']['mean'][0]==1
    with pytest.raises(ValueError):initial_state(parent,'unknown')
