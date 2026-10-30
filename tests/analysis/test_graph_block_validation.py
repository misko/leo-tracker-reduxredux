import numpy as np
import pytest
from validate_graph_inclusion_blocks import masks


def test_graph_block_masks_exclude_target_and_every_held_value_from_control():
    old=np.ones(20,bool);train=np.tile([True]*4+[False]*6,2);held=~train
    original=old.copy();control,addition,test=masks(old,train,held,slice(10,20),[slice(0,10),slice(10,20)])
    assert control.sum()==4 and addition.sum()==8 and test.sum()==6
    assert not control[10:].any() and not (addition&held).any()
    np.testing.assert_array_equal(old,original)
    with pytest.raises(ValueError):masks(old,train,np.ones(20,bool),slice(10,20),[slice(0,10),slice(10,20)])


def test_tiny_training_groups_do_not_calibrate_but_their_held_rows_remain():
    old=np.ones(20,bool);train=np.zeros(20,bool);train[:3]=True;train[10:18]=True
    c,a,h=masks(old,train,~train,slice(10,20),[slice(0,10),slice(10,20)])
    assert not c.any() and a.sum()==8 and h.sum()==7


def test_exact_gate_replay_supports_curved_only_problem_and_restores_it(monkeypatch):
    from types import SimpleNamespace
    import audit_explicit_phase_endpoint as module
    c=dict(conditional_residual_hz=np.ones(4)*10)
    calculate=lambda _:c
    frequency=lambda _:(np.zeros(4),np.ones(4)*30)
    p=SimpleNamespace(calculate=calculate,conditional_frequency=frequency,explicit_phase_family=7,
        rows=[dict(candidate_index=7)],members=[0],slices=[slice(0,4)],q=np.ones(4),keep=np.ones(4,bool),
        scan=SimpleNamespace(tracks=[dict(key='curve',times=np.arange(4.))]))
    monkeypatch.setattr(module,'family_frequency',lambda *a,**kw:(np.ones(4)*3,np.ones(4)*30))
    def gates(p,x,entries):
        np.testing.assert_array_equal(p.calculate(x)['conditional_residual_hz'],np.ones(4)*7)
        assert not entries
        return dict(test=1.)
    monkeypatch.setattr(module,'gate_slacks',gates)
    result=module.exact_gate_replay(p,[0,0],[])
    assert result['all_pass'] and result['family_witnesses'][0]['RMS_hz']==7
    assert p.calculate is calculate and p.conditional_frequency is frequency
