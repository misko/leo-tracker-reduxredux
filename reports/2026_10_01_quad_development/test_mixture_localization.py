import numpy as np
from test_shared_scale_port import members
from mixture_localization import MixtureObjective
from shared_scale_port import SharedScalePort


def model(mode, groups=(0, 0)):
    pairs = members(); x = np.array([.3, -.4, .2]); precision = np.array([0., 0., 2.])
    return MixtureObjective([p for p,i in pairs], [i for p,i in pairs], groups, precision, x, mode), x, pairs


def test_independent_and_shared_physical_objective_endpoints():
    for mode in ('independent', 'shared'):
        m, x, pairs = model(mode)
        scores = sum(p.score_selected(x, i) for p,i in pairs) if mode == 'independent' else SharedScalePort(pairs).score_selected(x, 0)
        np.testing.assert_allclose(m.evaluate(x)[0], .5*(m.precision*x)@x-scores, atol=1e-12)


def test_mixture_state_gradient_including_prior():
    m, x, _ = model('mixture'); _, gradient, H, _ = m.evaluate(x)
    numeric = []
    for j in m.active:
        step = np.eye(3)[j]*1e-5
        numeric.append((m.evaluate(x+step, False)[0]-m.evaluate(x-step, False)[0])/2e-5)
    np.testing.assert_allclose(gradient, numeric, atol=1e-8)
    np.linalg.cholesky(H)


def test_singleton_groups_preserve_value_gradient_and_metric():
    a, x, _ = model('independent', (0, 1)); b, _, _ = model('mixture', (0, 1))
    for left, right in zip(a.evaluate(x)[:3], b.evaluate(x)[:3]): np.testing.assert_allclose(left, right, atol=1e-12)
