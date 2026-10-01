import time
from types import SimpleNamespace
import numpy as np
from shared_visibility_curvature_optimizer import fit,residual_rows


class Quadratic:
    precision=np.array([0.,0.,4.])
    rows=np.array([[1.,.2,.3],[.1,2.,.4],[.2,.1,.7]])
    def evaluate(self,x,assigned=None,gradient=True):
        if np.linalg.norm(x[:2])>250:raise ValueError('outside prior')
        delta=x-np.array([3.,-2.,.5]);h=np.diag(self.precision)+self.rows.T@self.rows
        return float(.5*delta@h@delta),h@delta if gradient else None,(0,)


def test_preconditioned_direction_recovers_coupled_quadratic():
    model=Quadratic()
    result=fit(model,[4.,-1.,1.],time.monotonic()+5,rows_function=lambda m,x,l:m.rows)
    assert result['converged'] and result['iterations']==1
    np.testing.assert_allclose(result['mean'],[3,-2,.5],atol=1e-10)
    assert np.all(np.diff(result['objectives'])<0)


def test_expired_deadline_and_unidentifiable_geometry_are_unresolved():
    model=Quadratic()
    result=fit(model,[4,-1,1],time.monotonic()-1)
    assert result['reason']=='wall_budget' and not result['converged']
    result=fit(model,[4,-1,1],time.monotonic()+5,rows_function=lambda m,x,l:np.zeros((1,3)))
    assert result['reason']=='curvature_failed' and not result['converged']


def test_whitening_mapping_and_background_exclusion():
    covariance=np.array([[2.,.5],[.5,3.]])
    jac=np.array([[1.,2.,3.],[4.,5.,6.]])
    prediction=SimpleNamespace(mean=np.zeros(2),covariance=covariance,jacobian=jac)
    port=SimpleNamespace(candidate_count=1,observation=np.array([1.,-2.]),
        original=SimpleNamespace(predict_selected=lambda x,i:prediction))
    model=SimpleNamespace(ports=[port,port],columns=[np.array([0,1,3]),np.array([0,1,2])])
    result=residual_rows(model,np.zeros(4),(0,1))
    full=np.zeros((2,4));full[:,[0,1,3]]=jac
    weight=6/(4+float(port.observation@np.linalg.solve(covariance,port.observation)))
    np.testing.assert_allclose(result.T@result,weight*full.T@np.linalg.solve(covariance,full))
