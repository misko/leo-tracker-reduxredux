import time
import numpy as np
from shared_visibility_optimizer import fit


class Quadratic:
    precision=np.array([0.,0.,4.])
    def evaluate(self,x,assigned=None,gradient=True):
        if np.linalg.norm(x[:2])>250:raise ValueError('outside prior')
        delta=x-np.array([3.,-2.,.5]);h=np.array([[2.,.3,0],[.3,1.,.2],[0,.2,5.]])
        return float(.5*delta@h@delta),h@delta if gradient else None,(0,)


def test_full_gradient_solver_decreases_and_recovers_coupled_optimum():
    result=fit(Quadratic(),[20,10,2],time.monotonic()+5,max_iterations=100)
    assert result['converged']
    np.testing.assert_allclose(result['mean'],[3,-2,.5],atol=1e-4)
    assert np.all(np.diff(result['objectives'])<=0)


def test_expired_deadline_preserves_unresolved_outcome():
    result=fit(Quadratic(),[20,10,2],time.monotonic()-1)
    assert not result['converged'] and result['reason']=='wall_budget' and result['iterations']==0
