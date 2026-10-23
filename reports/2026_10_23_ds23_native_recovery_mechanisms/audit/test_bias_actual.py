"""Fixed-position recorded-evidence audit; no fitting or phase refresh."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'solver0365'/'bias_prior'))
import run_bias as b
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from diagnostics import dense_prediction


def test_actual0259_mixed_bias_retains_shared_covariance_and_curved_calibration():
    d, kind, primary, frozen, selected = b.s.setup('DS23-0259')
    parent = frozen['ordinary_graph']['entries']
    original = {e['component'] for e in parent}
    try:
        for arm in ('c0', 'fitted_c'):
            saved = primary['arms'][arm]
            x = np.asarray(saved['endpoint_east_north_km'])
            b.configure(d['entries'], parent, 300)
            p = b.s.exp.paths.build(d, kind, arm, saved['phase_reference'])
            before = p.calculate(x)
            config = b.configure(d['entries'], parent, 600)
            # build() memoizes by position: construct a fresh problem when the
            # globally configured predictive prior changes.
            p = b.s.exp.paths.build(d, kind, arm, saved['phase_reference'])
            after = p.calculate(x)
            curved = p.curved_calculate(x)
            np.testing.assert_array_equal(before['coefficient'], after['coefficient'])
            assert before['curved_negative_twice_elbo'] == after['curved_negative_twice_elbo']
            assert all(s == (300 if e['component'] in original else 600)
                       for e,s in zip(d['entries'],config['entry_bias_sigmas_hz'],strict=True))
            view, values, sigma, groups, slices = linear_geometry(p,d['entries'])
            assert not p.events
            geometry=geometry_features(view,x,0.)
            u=geometry['features'];g=p.noise_groups[p.keep];train=curved['features'][p.keep]
            weights=np.asarray(d['powers'])[g]*curved['noise_precision'][g]/p.point_noise[p.keep]**2
            gram=np.diag(curved['coefficient_prior_precision'])+train.T@(train*weights[:,None])
            c=np.linalg.inv(gram)
            raw=values-view.q*geometry['intercept']-u@curved['coefficient']
            dense=dense_prediction(raw,u,c,sigma*np.sqrt(2),groups,bias_sigma=0.)
            covariance=dense['covariance_hz2'].copy()
            for sl,sd in zip(slices,config['entry_bias_sigmas_hz'],strict=True):
                covariance[sl,sl]+=sd**2
            score=float(raw@np.linalg.solve(covariance,raw)+np.linalg.slogdet(covariance)[1]+len(raw)*np.log(2*np.pi))
            np.testing.assert_allclose(score,after['linear_predictive_objective'],rtol=0,atol=2e-5)
            cross=u[slices[0]]@c@u[slices[-1]].T
            assert np.max(np.abs(cross)) > 0
            np.testing.assert_allclose(covariance[slices[0],slices[-1]],cross,rtol=1e-10,atol=1e-8)
    finally:
        b.events.predictive_residual=b.original_predictive_residual
