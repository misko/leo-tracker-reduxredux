import numpy as np
import pytest
from scipy.linalg import block_diag
from scipy.special import logsumexp
from scipy.stats import multivariate_normal
from leo.analysis.research.joint_predictive_families import two_family_phase_evidence
from leo.analysis.research.predictive_track import phase_mixture_evidence


def fixture(cross=True):
    rng=np.random.default_rng(93);y=[rng.normal(size=3),rng.normal(size=2)]
    means=[rng.normal(size=(3,3)),rng.normal(size=(4,2))];u=[rng.normal(size=(3,3,2))*.4,rng.normal(size=(4,2,1))*.3]
    h=rng.normal(size=(5,2));b=np.eye(5)+h@h.T
    if not cross:b=block_diag(b[:3,:3],b[3:,3:])
    lp=[np.log([.2,.3,.5]),np.log([.1,.2,.3,.4])];vis=[np.array([True,False,True]),np.ones(4,bool)]
    return y,means,b,u,lp,vis


def test_matches_full_gaussian_oracle_and_chunking():
    args=fixture();y,m,b,u,lp,vis=args;table=np.full((3,4),-np.inf);coefficients={}
    for i in range(3):
        for j in range(4):
            modes=block_diag(u[0][i],u[1][j]);residual=np.concatenate(y)-np.r_[m[0][i],m[1][j]]
            covariance=b+modes@modes.T
            if vis[0][i] and vis[1][j]:table[i,j]=multivariate_normal.logpdf(residual,cov=covariance)+lp[0][i]+lp[1][j]
            coefficients[i,j]=modes.T@np.linalg.solve(covariance,residual)
    score=logsumexp(table);weights=np.exp(table-score);k=np.unravel_index(np.argmax(table),table.shape)
    for chunk in (4,32768):
        r=two_family_phase_evidence(*args,max_pairs=chunk)
        assert r['negative_twice_log_density']==pytest.approx(-2*score,abs=1e-11)
        np.testing.assert_allclose(r['phase_marginals'][0],weights.sum(axis=1),atol=1e-12)
        np.testing.assert_allclose(r['phase_marginals'][1],weights.sum(axis=0),atol=1e-12)
        np.testing.assert_allclose(np.concatenate(r['orbital_map_mean']),coefficients[k],atol=1e-12)
        assert r['visible_prior_mass']==pytest.approx(.7)


def test_independent_sum_only_when_cross_covariance_is_zero():
    for cross in (False,True):
        y,m,b,u,lp,v=fixture(cross)
        score=two_family_phase_evidence(y,m,b,u,lp,v)['negative_twice_log_density']
        marginal=sum(phase_mixture_evidence(y[k],m[k],b[sl,sl],u[k],lp[k],v[k])['negative_twice_log_density'] for k,sl in enumerate((slice(0,3),slice(3,5))))
        if not cross:assert score==pytest.approx(marginal,abs=1e-11)
        else:assert abs(score-marginal)>.01


def test_family_order_invariance_and_invisible_mass():
    y,m,b,u,lp,v=fixture();indices=[3,4,0,1,2]
    first=two_family_phase_evidence(y,m,b,u,lp,v)
    second=two_family_phase_evidence(y[::-1],m[::-1],b[np.ix_(indices,indices)],u[::-1],lp[::-1],v[::-1])
    assert first['negative_twice_log_density']==pytest.approx(second['negative_twice_log_density'],abs=1e-11)
    np.testing.assert_allclose(first['phase_marginals'][0],second['phase_marginals'][1],atol=1e-12)
    v[0][:]=False;r=two_family_phase_evidence(y,m,b,u,lp,v)
    assert r['negative_twice_log_density']==np.inf
    assert all(not w.any() for w in r['phase_marginals'])


def test_invalid_covariance_rejected():
    args=list(fixture());args[2][0,1]+=1
    with pytest.raises(ValueError,match='symmetric'):two_family_phase_evidence(*args)
