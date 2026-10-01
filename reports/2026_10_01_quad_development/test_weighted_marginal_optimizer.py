import time
import numpy as np
from weighted_marginal_optimizer import fit


class Quadratic:
    precision=np.array([0.,0.,4.])
    h=np.array([[2.,.3,.1],[.3,1.,.2],[.1,.2,5.]])
    def evaluate(self,x,assigned=None,gradient=True):
        d=x-np.array([3.,-2.,.5])
        return float(.5*d@self.h@d),self.h@d if gradient else None,(0,)


def test_descent_direction_recovers_coupled_optimum():
    result=fit(Quadratic(),[4.,-1.,1.],time.monotonic()+5,
        direction_function=lambda m,x,g:-np.linalg.solve(m.h,g))
    assert result['converged'] and result['iterations']==1
    np.testing.assert_allclose(result['mean'],[3.,-2.,.5],atol=1e-10)


def test_nondescent_and_expired_budget_remain_failures():
    result=fit(Quadratic(),[4.,-1.,1.],time.monotonic()+5,direction_function=lambda m,x,g:g)
    assert not result['converged'] and result['reason']=='non_descent'
    result=fit(Quadratic(),[4.,-1.,1.],time.monotonic()-1)
    assert not result['converged'] and result['reason']=='wall_budget'
