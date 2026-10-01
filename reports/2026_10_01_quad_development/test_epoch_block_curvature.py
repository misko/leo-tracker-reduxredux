import numpy as np
import pytest
from epoch_block_curvature import solve_blocks


def test_two_scan_weighted_candidate_blocks_match_dense_solve():
    rng=np.random.default_rng(751);maps=[np.arange(8),np.r_[0,1,np.arange(8,15)]]
    precision=np.r_[0.,0.,np.exp(rng.normal(size=13))];g=rng.normal(size=15)
    dense=np.diag(precision);blocks=[]
    for columns in maps:
        jac=rng.normal(size=(len(columns)-5,4,6));weights=rng.uniform(.01,1,len(jac))
        local=np.einsum('nmi,nmj->nij',jac,jac)*weights[:,None,None];blocks.append(local)
        for i,block in enumerate(local):
            indices=np.r_[columns[:5],columns[5+i]];dense[np.ix_(indices,indices)]+=block
    answer=solve_blocks(precision,maps,blocks,g)
    np.testing.assert_allclose(answer,np.linalg.solve(dense,g),atol=1e-10,rtol=1e-10)
    assert g@answer>0


def test_no_signal_geometry_remains_unresolved():
    with pytest.raises(np.linalg.LinAlgError):
        solve_blocks(np.r_[0.,0.,np.ones(4)],[np.arange(6)],[np.zeros((1,6,6))],np.ones(6))
