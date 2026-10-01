import numpy as np
from marginal_visibility_port import normalized_mass,visibility_mixture_gradient,residual_mixture_gradient
from visibility_state_gradient import weight_components,selected_weight_gradient


def test_visibility_expectation_matches_all_expanded_branch_gradients():
    margins=np.array([[.1,.3],[-.2,.5],[.6,.9]])
    jac=np.arange(18,dtype=float).reshape(3,2,3)/30
    components=weight_components(margins,jac,.1,.9)
    p=np.array([.1,.2,.3,.4])
    expected=sum(p[i]*selected_weight_gradient(components,i) for i in range(4))
    np.testing.assert_allclose(visibility_mixture_gradient(p,components),expected)


def test_full_marginal_residual_gradient_matches_finite_differences():
    rng=np.random.default_rng(918);count=4;dim=3
    jac=rng.normal(size=(count,dim,6));means=rng.normal(size=(count,dim))
    observation=np.array([.2,-.4,.7]);precision=np.eye(dim)
    def value(state):
        local=np.column_stack([np.broadcast_to(state[:5],(count,5)),state[5:]])
        residual=observation-means-np.einsum('nmc,nc->nm',jac,local)
        scores=-(4+dim)/2*np.log1p(np.sum(residual**2,axis=1)/4)
        marginal,p=normalized_mass(np.r_[scores,-3.])
        return marginal,residual,p
    state=rng.normal(size=5+count)/10;_,residual,p=value(state)
    gradient=residual_mixture_gradient(p[:-1],residual,precision,jac)
    numeric=[]
    for i in range(len(state)):
        d=np.eye(1,len(state),i)[0]*1e-5
        numeric.append((value(state+d)[0]-value(state-d)[0])/2e-5)
    np.testing.assert_allclose(gradient,numeric,atol=1e-8,rtol=1e-7)
