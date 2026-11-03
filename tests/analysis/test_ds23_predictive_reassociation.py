import itertools
import numpy as np
import pytest

from ds23_predictive_reassociation import block_objective,select_assignment,curved_alias,family_pattern_product
from leo.analysis.research.retained_track_likelihood import PERIOD
from ds23_predictive_linear import predictive_residual


def test_block_density_reproduces_shared_calibration_marginal_exactly():
    rng=np.random.default_rng(1317);n=13;width=4
    raw=rng.normal(size=n);u=rng.normal(size=(n,width));a=rng.normal(size=(width,width))
    gram=a@a.T+np.eye(width);sigma=rng.uniform(.5,2,n)
    uncertainty=np.linalg.solve(np.linalg.cholesky(gram),u.T).T
    blocks=[dict(raw=raw[sl],uncertainty=uncertainty[sl],sigma=sigma[sl]) for sl in (slice(0,6),slice(6,13))]
    result=predictive_residual(raw,u,gram,sigma,np.r_[np.zeros(6,int),np.ones(7,int)],bias_sigma=3.)
    assert block_objective(blocks,bias_sigma_hz=3.)==pytest.approx(result['objective'],abs=1e-10)


def test_joint_assignment_can_disagree_with_independent_scores_and_keeps_inputs():
    def block(value,incumbent=False):
        return dict(raw=np.full(5,value),uncertainty=np.ones((5,1))*1000,
                    sigma=np.ones(5)*10,incumbent=incumbent)
    pools=[[block(900),block(-1000)],[block(-900),block(1000,True)]]
    original=[[b['raw'].copy() for b in pool] for pool in pools]
    result=select_assignment(pools,top_k=1,sweeps=3)
    # The incumbent prevents the second track's positive alternative being
    # pruned; common calibration uncertainty rewards a consistent pair.
    assert result['indices']==[0,1]
    assert result['objective']<block_objective([pools[0][0],pools[1][0]])
    assert all(b['raw'].tolist()==r.tolist() for pool,refs in zip(pools,original,strict=True) for b,r in zip(pool,refs,strict=True))
    assert all(b['objective']<=a['objective']+1e-8 for a,b in zip(result['history'][:-1],result['history'][1:],strict=True))


def test_invalid_pools_or_noise_fail_closed():
    with pytest.raises(ValueError):select_assignment([[]])
    with pytest.raises(ValueError):block_objective([dict(raw=np.zeros(2),uncertainty=np.zeros((2,1)),sigma=np.array([1.,-1.]))])


def test_alias_counts_periods_not_hertz_and_uses_independent_noise():
    for k in range(-5,6):
        r=np.array([k*PERIOD+100.,k*PERIOD-120.,k*PERIOD+10.])
        assert curved_alias(r,np.array([50.,60.,70.]))==-k
    assert curved_alias(np.array([0.,PERIOD]),np.array([1.,1000.]))==0


def test_family_patterns_recombine_without_changing_physical_rows_or_input():
    def node(labels):
        return dict(seed=dict(rows=[dict(component=k,candidate_index=j,candidate_norad=100+j) for k,j in zip(['a','b','c'],labels,strict=True)]),aliases=[0,1,0])
    nodes=[node([1,2,3]),node([4,2,8]),node([1,5,9])]
    result,receipt=family_pattern_product(nodes,{'a','b'})
    assert receipt['hypotheses']==4
    assert {tuple(r['candidate_index'] for r in n['seed']['rows']) for n in result}=={(1,2,3),(1,5,3),(4,2,3),(4,5,3)}
    assert [r['candidate_index'] for r in nodes[0]['seed']['rows']]==[1,2,3]
    assert all(n['aliases']==[0,1,0] for n in result)
    with pytest.raises(ValueError,match='cap'):family_pattern_product(nodes,{'a','b'},maximum=3)
