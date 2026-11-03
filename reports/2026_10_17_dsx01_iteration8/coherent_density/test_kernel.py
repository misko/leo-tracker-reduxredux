import unittest

import numpy as np

from kernel import coherent_terms


class CoherentDensityTests(unittest.TestCase):
    def test_small_group_matches_enumerated_point_clutter_and_identity(self):
        alias, sigma, eta, epsilon = 10., .6, .1, .12
        y = np.array([.2, -.4])
        pred = np.array([[.0, 2.], [.1, -1.]])
        w = np.array([[.8, .3], [.9, .6]])
        q = np.array([.2, .7])
        terms = coherent_terms(y, pred, w, q, [5, 5], sigma_hz=sigma, alias_hz=alias)
        r = y[:, None]-pred
        phi = sum(np.exp(-.5*((r+i*alias)/sigma)**2)/(sigma*np.sqrt(2*np.pi)) for i in range(-4, 5))
        a, u = 1-epsilon, 1/alias
        per_identity, numerators = [], np.zeros_like(w)
        for s in range(2):
            total = 0.
            for mask in range(4):
                value = (1-eta)*q[s]/q.sum()
                for n in range(2):
                    value *= a*w[n,s]*phi[n,s] if mask & (1<<n) else (1-a*w[n,s])*u
                total += value
                for n in range(2):
                    if mask & (1<<n):numerators[n,s] += value
            per_identity.append(total)
        density = eta*u**2+sum(per_identity)
        self.assertAlmostEqual(terms.nll, -np.log(density), places=13)
        np.testing.assert_allclose(terms.group_posterior[0], np.r_[eta*u**2, per_identity]/density)
        np.testing.assert_allclose(terms.signal_responsibility, numerators/density)
        np.testing.assert_allclose(terms.clutter_probability, 1-terms.signal_responsibility.sum(axis=1))

    def test_normalized_torus_quadrature_singleton_and_two_point_group(self):
        alias, bins = 8., 64
        grid = (np.arange(bins)+.5)*alias/bins-alias/2
        yy = np.stack(np.meshgrid(grid, grid, indexing='ij'), axis=-1).reshape(-1)
        count = bins*bins
        pred = np.tile(np.array([[.1, -1.2], [1.1, -.4]]), (count, 1))
        w = np.tile(np.array([[.2, 1.], [.9, .4]]), (count, 1))
        terms = coherent_terms(yy, pred, w, [.3, .8], np.repeat(np.arange(count), 2),
            sigma_hz=np.tile([.45, .65], count), alias_hz=alias)
        self.assertAlmostEqual(np.exp(-terms.group_nll).sum()*(alias/bins)**2, 1., places=12)
        single = coherent_terms(grid, np.tile([.1, -1.2], (bins, 1)),
            np.tile([.2, 1.], (bins, 1)), [.3, .8], np.arange(bins), sigma_hz=.45, alias_hz=alias)
        self.assertAlmostEqual(np.exp(-single.group_nll).sum()*alias/bins, 1., places=12)

    def test_singleton_closed_form_uses_own_normalized_point_counterpart(self):
        alias, eta, epsilon = 10., .1, .12
        y = np.array([.2, -.4])
        pred = np.array([[.0, 2.], [.1, -1.]])
        w, q = np.array([[.8, .3], [.9, .6]]), np.array([.2, .7])
        sigma = np.array([[.6, .8], [.7, .9]])
        terms = coherent_terms(y,pred,w,q,[0,1],sigma_hz=sigma,alias_hz=alias)
        r = y[:,None]-pred
        phi = sum(np.exp(-.5*((r+i*alias)/sigma)**2)/(sigma*np.sqrt(2*np.pi)) for i in range(-4,5))
        signal = (1-eta)*(q/q.sum())*(1-epsilon)*w*phi
        uniform = (eta+(1-eta)*np.sum((q/q.sum())*(1-(1-epsilon)*w),axis=1))/alias
        density = uniform+signal.sum(axis=1)
        np.testing.assert_allclose(terms.group_nll,-np.log(density),rtol=1e-14,atol=1e-14)
        np.testing.assert_allclose(terms.signal_responsibility,signal/density[:,None])
        np.testing.assert_allclose(terms.clutter_probability,uniform/density)

    def test_all_three_gradients_and_q_normalization(self):
        y = np.array([.2, -.4, 2.1, -.2])
        pred = np.array([[.0, 2.], [.1, -1.], [.8, -.2], [.4, -.3]])
        w = np.array([[.8, .3], [.9, .6], [.5, .7], [.2, .4]])
        q = np.array([.2, .7])
        kwargs = dict(group_labels=[7, 7, 9, 7], sigma_hz=[.6, .8, .7, .9], alias_hz=10.)
        terms = coherent_terms(y, pred, w, q, **kwargs)
        for target, gradient, position in [(pred, terms.prediction_gradient, 0), (w, terms.visibility_gradient, 1), (q, terms.q_gradient, 2)]:
            numeric = np.empty_like(target)
            for idx in np.ndindex(target.shape):
                minus, plus = target.copy(), target.copy()
                minus[idx] -= 1e-5;plus[idx] += 1e-5
                low, high = [pred, w, q], [pred, w, q]
                low[position] = minus;high[position] = plus
                numeric[idx] = (coherent_terms(y, *high, **kwargs).nll-coherent_terms(y, *low, **kwargs).nll)/2e-5
            np.testing.assert_allclose(gradient, numeric, rtol=2e-7, atol=2e-9)
        scaled = coherent_terms(y, pred, w, 17*q, **kwargs)
        self.assertAlmostEqual(terms.nll, scaled.nll, places=13)
        np.testing.assert_allclose(terms.q_gradient/17, scaled.q_gradient, rtol=1e-12, atol=1e-14)
        self.assertAlmostEqual(np.dot(q, terms.q_gradient), 0., places=13)

    def test_invisible_uniform_limit_and_boundary_visibility_derivatives(self):
        alias = 10.
        y, pred, q = np.array([.2, -.4]), np.array([[0., 2.], [.1, -1.]]), np.array([.2, .7])
        w = np.zeros((2, 2))
        terms = coherent_terms(y, pred, w, q, ['arc', 'arc'], sigma_hz=.6, alias_hz=alias)
        self.assertAlmostEqual(terms.nll, 2*np.log(alias), places=13)
        np.testing.assert_allclose(terms.group_posterior[0], [.1, .9*.2/.9, .9*.7/.9], atol=1e-15)
        np.testing.assert_array_equal(terms.prediction_gradient, np.zeros((2,2)))
        np.testing.assert_array_equal(terms.signal_responsibility, np.zeros((2,2)))
        np.testing.assert_allclose(terms.clutter_probability, 1.)
        np.testing.assert_allclose(terms.q_gradient, 0., atol=1e-15)
        for boundary in [0., 1.]:
            w = np.full((2,2), boundary)
            t = coherent_terms(y, pred, w, q, [0,0], sigma_hz=.6, alias_hz=alias)
            step = 1e-6 if boundary == 0 else -1e-6
            nearby = w.copy();nearby[0,1] += step
            other = coherent_terms(y, pred, nearby, q, [0,0], sigma_hz=.6, alias_hz=alias)
            self.assertAlmostEqual((other.nll-t.nll)/step, t.visibility_gradient[0,1], delta=3e-6)

    def test_alias_invariance_seam_gradient_and_broad_wrapped_normal(self):
        alias = 10.
        y, pred, w, q = np.array([4.999, -.01]), np.array([[0., 1.], [4.99, -.4]]), np.ones((2,2)), [.4, .6]
        base = coherent_terms(y, pred, w, q, [0,0], sigma_hz=2.8, alias_hz=alias)
        moved = coherent_terms(y+np.array([3., -7.])*alias, pred+np.array([[2.,-3.],[1.,4.]])*alias,
            w, q, [0,0], sigma_hz=2.8, alias_hz=alias)
        for name in ['group_nll','prediction_gradient','visibility_gradient','q_gradient','signal_responsibility']:
            np.testing.assert_allclose(getattr(base,name), getattr(moved,name), rtol=1e-12, atol=1e-13)
        p = pred.copy();p[0,0] += 1e-5
        m = pred.copy();m[0,0] -= 1e-5
        fd = (coherent_terms(y,p,w,q,[0,0],sigma_hz=2.8,alias_hz=alias).nll-
            coherent_terms(y,m,w,q,[0,0],sigma_hz=2.8,alias_hz=alias).nll)/2e-5
        self.assertAlmostEqual(fd, base.prediction_gradient[0,0], places=10)
        broad = coherent_terms(y,pred,w,q,[0,0],sigma_hz=10*alias,alias_hz=alias)
        self.assertAlmostEqual(broad.nll, 2*np.log(alias), places=12)
        np.testing.assert_allclose(broad.prediction_gradient, 0., atol=1e-15)

    def test_partition_row_order_relabeling_and_singleton_counterpart(self):
        y = np.array([.2, -.4, .3])
        pred = np.array([[.0, 2.], [.1, -1.], [.5, -.4]])
        w = np.array([[.8, .3], [.9, .6], [.3, .4]])
        q = [.2, .7]
        labels = np.array([7, 3, 7])
        base = coherent_terms(y,pred,w,q,labels,sigma_hz=.6,alias_hz=10.)
        perm = np.array([2,0,1])
        other = coherent_terms(y[perm],pred[perm],w[perm],q,labels[perm],sigma_hz=.6,alias_hz=10.)
        renamed = coherent_terms(y,pred,w,q,['x','y','x'],sigma_hz=.6,alias_hz=10.)
        self.assertEqual(base.group_labels, (7,3))
        self.assertAlmostEqual(base.nll, other.nll, places=13)
        self.assertAlmostEqual(base.nll, renamed.nll, places=13)
        np.testing.assert_allclose(base.prediction_gradient[perm], other.prediction_gradient)
        np.testing.assert_allclose(base.signal_responsibility[perm], other.signal_responsibility)
        singleton = coherent_terms(y,pred,w,q,np.arange(3),sigma_hz=.6,alias_hz=10.)
        separate = [coherent_terms(y[i:i+1],pred[i:i+1],w[i:i+1],q,[0],sigma_hz=.6,alias_hz=10.) for i in range(3)]
        self.assertAlmostEqual(singleton.nll, sum(t.nll for t in separate), places=13)
        self.assertAlmostEqual(base.nll, base.group_nll.sum(), places=13)
        np.testing.assert_allclose(base.group_posterior.sum(axis=1), 1.)
        np.testing.assert_allclose(base.signal_responsibility.sum(axis=1)+base.clutter_probability, 1.)

    def test_long_group_is_stable_without_product_underflow(self):
        n = 3000
        terms = coherent_terms(np.zeros(n), np.zeros((n,2)), np.ones((n,2)), [.2,.7],
            np.zeros(n,int),sigma_hz=125.)
        self.assertTrue(np.isfinite(terms.nll))
        for name in ['prediction_gradient','visibility_gradient','q_gradient','group_posterior','signal_responsibility']:
            self.assertTrue(np.all(np.isfinite(getattr(terms,name))))
        self.assertAlmostEqual(terms.group_posterior.sum(), 1., places=11)
        self.assertFalse(hasattr(terms,'row_nll'))

    def test_invalid_partition_and_probability_inputs_are_explicit(self):
        good = (np.zeros(2), np.zeros((2,2)), np.ones((2,2)), [.2,.7], [0,0])
        for labels in [[0], [[0],[0]], [0,np.nan], [None,0], [0,np.inf]]:
            with self.assertRaises(ValueError):coherent_terms(*good[:4],labels)
        for q in [[0.,1.],[-1.,2.],[np.inf,1.],[0.,0.]]:
            with self.assertRaises(ValueError):coherent_terms(*good[:3],q,good[4])
        for kw in [dict(eta=0),dict(eta=1),dict(epsilon=0),dict(epsilon=1),dict(alias_hz=0),dict(sigma_hz=-1),dict(sigma_hz=[1,2,3])]:
            with self.assertRaises(ValueError):coherent_terms(*good,**kw)
        with self.assertRaises(ValueError):coherent_terms(good[0],good[1],np.full((2,2),1.1),*good[3:])
        with self.assertRaises(ValueError):coherent_terms([np.nan,0.],*good[1:])


if __name__ == '__main__':
    unittest.main()
