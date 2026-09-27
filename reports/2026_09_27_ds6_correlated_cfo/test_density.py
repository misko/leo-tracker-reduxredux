import numpy as np
from scipy.stats import multivariate_t
from density import TrackDensity


def test_low_rank_density_matches_dense_multivariate_t():
    t=np.arange(8.);mask=np.arange(8)%2==0;r=np.array([t*3+40,t*7-12])
    for slope in [0.,3.]:
        model=TrackDensity(t,mask,slope,noise_scale=10.,offset_scale=100.)
        scores=model.scores(r);centered=t-t[mask].mean()
        for j,select in enumerate([mask,np.ones(8,dtype=bool)]):
            ts=centered[select];cov=np.eye(len(ts))*100+np.ones((len(ts),len(ts)))*10000+slope**2*np.outer(ts,ts)
            expected=multivariate_t.logpdf(r[:,select],shape=cov,df=4)
            np.testing.assert_allclose(scores[j],expected,atol=1e-9)


def test_large_offset_stability_and_training_isolation():
    t=np.linspace(0,300,50);mask=np.arange(50)%2==0
    model=TrackDensity(t,mask,8.);r=(1e6+7*t)[None,:]
    train,joint=model.scores(r);assert np.isfinite(train).all() and np.isfinite(joint).all()
    changed=r.copy();changed[:,~mask]+=1e8
    np.testing.assert_array_equal(model.scores(changed)[0],train)
    assert model.scores(changed)[1][0]<joint[0]
