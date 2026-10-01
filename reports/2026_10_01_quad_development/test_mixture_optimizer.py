import time
import numpy as np
from mixture_optimizer import fit, audit


class Quadratic:
    active = np.array([0, 1])
    def evaluate(self, x, derivatives=True):
        delta = x-np.array([2., -1.]); H = np.diag([2., 3.])
        return float(.5*delta@H@delta), H@delta, H, {}


def test_known_optimum_and_independent_audit():
    m = Quadratic(); result = fit(m, np.zeros(2), time.monotonic()+1)
    np.testing.assert_allclose(result['mean'], [2., -1.], atol=1e-12)
    assert result['converged'] and audit(m, result)['accepted']


def test_expired_deadline_preserves_failure():
    result = fit(Quadratic(), np.zeros(2), time.monotonic()-1)
    assert not result['converged'] and result['reason'] == 'wall_budget'
