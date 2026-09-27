import importlib.util
import json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('envelope',HERE/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_clock_boundary_difference_is_second_order():
    for clock in [-5.,0.,5.]:
        point=np.array([0.,0.,clock])
        def function(x):
            assert -5<=x[2]<=5
            return 10000*(x[2]-clock)**2+3*x[2]
        np.testing.assert_allclose(m.difference(function,point,2),3.,atol=1e-7)


def test_real_gradient_matches_independent_reprofiling():
    pm=m.previous.phase.Model();parent=m.ROOT/'2026_09_27_ds6_cohort_phase';r=json.loads((parent/'all.json').read_text());p=json.loads((parent/'all-protocol.json').read_text());source=json.loads((m.ROOT/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text());x=np.array(r['results']['cfo_only']['x']);ids=[p['sessions'].index(b['scan']['session_id'])+2 for b in pm.banks];x=np.r_[x[:2],x[ids]]
    models=[m.fresh.load_model(b['scan']['session_id'],source['center'])[0] for b in pm.banks];objective=m.Objective(models,pm,[2,3,4],'phase');value,gradient=objective.value_gradient(x)
    module=m.previous.phase.geo.pair.u;original=module.robust_scores
    def score(residual,mask,sigma=100.):
        a,b,_=m.solver.scores(residual,mask,sigma);return a,b
    module.robust_scores=score
    try:
        scale=(6371.0088*np.pi/180)/111.195
        def function(point):return -pm.evaluate(np.r_[point[:2]*scale,point[2:]],'phase')['train']
        np.testing.assert_allclose(value,function(x),atol=1e-6,rtol=0)
        expected=[]
        for i in range(len(x)):
            a=x.copy();b=x.copy();a[i]+=2e-5;b[i]-=2e-5;expected.append((function(a)-function(b))/4e-5)
        np.testing.assert_allclose(gradient,expected,atol=.05,rtol=1e-3)
    finally:module.robust_scores=original


def test_completed_full_cohort_refits():
    for arm in ['cfo_only','phase']:
        p=HERE/f'all-{arm}-protocol.json';r=json.loads((HERE/f'all-{arm}.json').read_text())
        assert r['complete'] and r['protocol_sha256']==m.fresh.digest(p)
        assert len(json.loads(p.read_text())['sessions'])==43 and len(r['x'])==45
        assert np.isfinite(r['train']) and np.isfinite(r['held'])


def test_exact_propagation_audit_covers_all_scans():
    r=json.loads((HERE/'propagation-audit.json').read_text());assert r['complete']
    p=json.loads((HERE/'all-cfo_only-protocol.json').read_text())
    assert [s['session_id'] for s in r['scans']]==p['sessions']
    for arm,digest in r['fit_hashes'].items():
        assert digest==m.fresh.digest(HERE/f'all-{arm}.json')
    for s in r['scans']:
        for arm in ['cfo_only','phase']:
            assert s['arms'][arm]['maximum_prediction_error_hz']<.1
            assert np.isfinite(s['arms'][arm]['train_change'])
            assert np.isfinite(s['arms'][arm]['held_change'])
