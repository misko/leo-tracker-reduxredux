import numpy as np
from joint_selection import select_joint


def row(values):return {'train':np.array(values,float)}


def test_penalty_prevents_marginal_switch_but_not_strong_switch():
    prior={'a':np.log([.5,.5]),'b':np.log([.5,.5])}
    opts={'t':{'a':row([0,0]),'b':row([2,2])}}
    assert select_joint(opts,{'t':'a'},prior,0)[0]['ids']['t']=='b'
    assert select_joint(opts,{'t':'a'},prior,3)[0]['ids']['t']=='a'
    assert select_joint(opts,{'t':'a'},prior,1)[0]['ids']['t']=='b'


def test_shared_evidence_and_convergence():
    prior={'a':np.log([.5,.5]),'b':np.log([.5,.5])}
    opts={'x':{'a':row([0,-20]),'b':row([2,2])},'y':{'a':row([-20,0]),'b':row([2,2])}}
    selected,receipt=select_joint(opts,{'x':'a','y':'a'},prior,1)
    assert selected['converged'] and all(r['converged'] for r in receipt['runs'])
    assert selected['ids']=={'x':'b','y':'b'}


def test_no_test_values_are_accepted_or_used():
    prior={'a':np.array([0.])};opts={'t':{'a':row([0])}}
    a=select_joint(opts,{'t':'a'},prior,2)[0]
    opts['t']['a']['test']=np.array([1e99])
    assert select_joint(opts,{'t':'a'},prior,2)[0]==a
