import numpy as np
import pytest
from fold_splice_audit import selected_curve,boundary_jumps,receiver_curves


def records():
    return [dict(arms={'fitted-c':{'parameters':[0,0,100*k,2,200*k,3]}},
        spline_nodes_s=[0,300],correction_knots_hz=[[5,5],[6,6]]) for k in range(5)]


def test_fold_selection_and_same_epoch_jumps():
    t=np.array([0.,9.999,10.,49.999,50.,299.99])
    curves=receiver_curves(records(),t,0)
    expected=100*np.array([0,0,1,4,0,4])+2*(t-150)+5
    np.testing.assert_allclose(selected_curve(curves,t),expected)
    times,jumps=boundary_jumps(records(),0)
    np.testing.assert_array_equal(jumps,np.where((times/10).astype(int)%5==0,-400,100))
    _,rx1=boundary_jumps(records(),1)
    np.testing.assert_array_equal(rx1,jumps*2)


def test_identical_models_have_no_switch_jump_despite_large_physical_rate():
    model=records()[0]
    _,jumps=boundary_jumps([model]*5,0)
    np.testing.assert_array_equal(jumps,0.)
    with pytest.raises(ValueError):selected_curve(np.zeros((4,3)),np.arange(3))
    with pytest.raises(ValueError):receiver_curves(records(),[0.],2)
