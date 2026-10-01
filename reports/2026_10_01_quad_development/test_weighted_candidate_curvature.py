from types import SimpleNamespace
import numpy as np
from weighted_candidate_curvature import candidate_blocks,curvature_direction


def test_full_candidate_weights_and_dense_direction():
    rng=np.random.default_rng(608);jac=rng.normal(size=(3,2,6));means=rng.normal(size=(3,2))
    covariance=np.array([[2.,.4],[.4,1.]]);precision=np.linalg.inv(covariance);observation=np.array([1.,-.5])
    probabilities=np.array([.2,.3,.1,.4])
    port=SimpleNamespace(candidate_count=3,observation=observation,likelihood=SimpleNamespace(precision=precision),
        score_all=lambda x:np.log(probabilities),
        original=SimpleNamespace(linearize_candidates=lambda x,indices:dict(means=means,jacobians=jac)))
    blocks=candidate_blocks(port,np.zeros(8));expected=[]
    for i in range(3):
        residual=observation-means[i]
        expected.append(probabilities[i]*6/(4+residual@precision@residual)*jac[i].T@precision@jac[i])
    np.testing.assert_allclose(blocks,expected,atol=1e-12)
    prior=np.r_[0.,0.,np.ones(6)];dense=np.diag(prior)
    for i,block in enumerate(expected):
        columns=np.r_[np.arange(5),5+i];dense[np.ix_(columns,columns)]+=block
    model=SimpleNamespace(ports=[port],columns=[np.arange(8)],precision=prior);gradient=rng.normal(size=8)
    actual=curvature_direction(model,np.zeros(8),gradient)
    np.testing.assert_allclose(actual,-np.linalg.solve(dense,gradient),atol=1e-10)
    assert gradient@actual<0
