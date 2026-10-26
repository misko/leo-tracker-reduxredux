"""Independent narrow position-policy preflight; no real target integrals."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCI = ROOT / 'position'
sys.path.insert(0, str(SCI))
import policy as e

read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    start = time.monotonic(); checks = []
    def check(name, passed, **details):
        checks.append(dict(name=name, passed=bool(passed), **details))
    protocol = read(SCI / 'protocol.json'); digest = sha(SCI / 'protocol.json')
    check('exact freeze and complete immutable scientific input bindings',
        digest == '60a2933eb2497d6f6b0b739f6fc22afe81070167649f5417a7845a1ee66963a0' and
        all(sha(path) == value for path, value in protocol['source_input_hashes'].items()),
        bindings=len(protocol['source_input_hashes']))
    smoke = read(SCI / 'load_smoke04.json')
    snapshot = SCI / 'smoke_source.py'
    def functions(path):
        return {n.name:ast.dump(n) for n in ast.parse(Path(path).read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    before, after = functions(snapshot), functions(SCI / 'policy.py')
    check('actual loaded-input/redacted-unknown smoke matches final science ports',
        smoke['all_passed'] and smoke['source_sha256'] == sha(snapshot) and
        all(before[n] == after[n] for n in ['load','Target','source_gate','attach','parent_view','context_smoke']) and
        smoke['actual_target_density_evaluations'] == 0 and
        [q['arm'] for q in smoke['checks']] == ['c0','fitted_c'] and
        all(max(q['errors'].values()) <= 1e-6 and q['scalar_residual_increment'] == 7 and q['full_ELBO_increment'] == 7 and
            q['original_predictive_points'] == 0 and not q['source_gate']['original_growth_supported'] and
            not q['source_gate']['original_target_active_points'] for q in smoke['checks']))
    metadata = read(e.OLD / 'prepared' / e.CASE / 'metadata.json')
    check('same whole20 IDs, eight inactive candidates and zero-removal original parent both arms',
        all(q['exact20_native_IDs'] == metadata['entry']['observation_ids'] and q['all8_absent_active'] and
            q['cavity_removed_IDs'] == [] for q in smoke['checks']) and len(metadata['pool']) == 8 and
        metadata['all8_families_absent_from_parent_likelihood'])
    status = pytest.main(['-q','-p','no:cacheprovider',str(SCI/'test_experiment.py')])
    check('eight owned density/scalar/cache/actual-port/control tests independently rerun', status == 0)
    # Nonempty E is absent in this real case, so exercise its conditional port
    # independently using a small complete C+E+T Gaussian system.
    rng = np.random.default_rng(202610260017)
    n, m, t, width = 13, 9, 6, 4
    fc = rng.normal(size=(n,width)); he = rng.normal(size=(m,width)); ht = rng.normal(size=(t,width))
    precision = rng.uniform(.8,1.8,width); coef = rng.normal(size=width)
    groups = np.arange(n)%2; powers = np.array([.7,1.2]); noise = np.array([.9,1.1]); sigma = rng.uniform(2.,4.,n)
    weights = powers[groups]*noise[groups]/sigma**2
    gram = np.diag(precision)+fc.T@(weights[:,None]*fc); v = np.linalg.inv(gram)
    ye, yt = rng.normal(size=m), rng.normal(size=t); se, st = rng.uniform(3.,5.,m), rng.uniform(2.,4.,t)
    ge = np.arange(m)%2
    parent = SimpleNamespace(keep=np.ones(n,bool),noise_groups=groups,point_noise=sigma,
        calculate=lambda x:dict(features=fc,coefficient_prior_precision=precision,coefficient=coef,noise_precision=noise))
    obj = e.Target.__new__(e.Target);obj.parent=parent;obj.d=dict(powers=powers);obj.ht=ht
    obj.values=yt+ht@coef;obj.sigma=st;obj.groups=np.zeros(t,int);obj.q=np.ones(t)
    obj.existing=(SimpleNamespace(q=np.ones(m)),ye+he@coef,se,ge,None)
    original_geometry=e.geometry_features
    try:
        e.geometry_features=lambda view,x,height:dict(features=he,intercept=np.zeros(m))
        got=obj.component((0.,0.))
    finally:
        e.geometry_features=original_geometry
        e.Target.component.cache_clear()
    ce=he@v@he.T+np.diag(2*se**2)+(ge[:,None]==ge[None,:])*300.**2
    ct=ht@v@ht.T+np.diag(2*st**2)+300.**2
    cross=ht@v@he.T
    expected_raw=yt-cross@np.linalg.solve(ce,ye)
    expected_cov=ct-cross@np.linalg.solve(ce,cross.T)
    mean_error=float(np.max(abs(got['raw']-expected_raw)));cov_error=float(np.max(abs(got['covariance']-expected_cov)))
    check('independent dense nonempty-predictive conditional matches actual Target.component port',
        mean_error<1e-8 and cov_error<1e-7 and np.array_equal(got['parent_coefficients'],coef) and
        np.array_equal(got['parent_noise'],noise),mean_error_hz=mean_error,covariance_error_hz2=cov_error)
    check('original5x48 common cold start, six bounded fits and exact operational fallback frozen',
        protocol['case']=='DS24-0011' and protocol['methods']==['no_addition','hard','mixture'] and
        protocol['position_fits']==6 and protocol['workers']==2 and protocol['BLAS_threads']==1 and
        protocol['per_method_fit_seconds']==60 and protocol['total_worker_seconds']==600 and
        abs(protocol['preparation_seconds']+2*protocol['arm_worker_seconds']-600)<1e-9 and
        protocol['scientific_retries']==0 and not protocol['GPS_before_RF_seal'] and
        'always exact original reference' in protocol['operational_policy'] and
        'endpointnorm<=.001km' in protocol['no_addition_reproduction'])
    check('frozen sources/inputs unchanged after pure synthetic audit',
        all(sha(path)==value for path,value in protocol['source_input_hashes'].items()))
    result=dict(all_passed=all(q['passed'] for q in checks),protocol_sha256=digest,checks=checks,
        seconds=time.monotonic()-start,source_sha256=sha(__file__),real_target_integrals=0,orbit_propagation_calls=0,
        position_fits=0,geographic_truth_read=False,
        scope='Launch authority for a diagnostic position comparison; original one-owner support failure forces operational baseline.')
    with (ROOT/'audit/preflight.json').open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(all_passed=result['all_passed'],checks=len(checks),seconds=result['seconds'],failed=[q for q in checks if not q['passed']])))


if __name__=='__main__':
    main()
