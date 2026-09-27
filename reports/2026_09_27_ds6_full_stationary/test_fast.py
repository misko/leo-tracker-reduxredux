import importlib.util
from pathlib import Path
import numpy as np
from fast_solver import fit,scores

path=Path(__file__).resolve().parent.parent/'2026_09_27_ds6_stationary_offsets/solver.py'
spec=importlib.util.spec_from_file_location('scalar_offset_oracle',path)
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)


def test_fast_matches_scalar_for_multimodal_and_translated_inputs():
    rng=np.random.default_rng(2026092741)
    for i in range(40):
        n=10+i*3
        train=rng.standard_t(4,n)*rng.choice([20.,100.,1000.])+rng.choice([-1e6,0.,1e6])
        train[:n//3]+=rng.choice([0.,500.,3000.])
        expected,a=oracle.fit(train);actual,b=fit(train)
        np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-6)
        assert b['converged'] and b['curvature']>0


def test_vectorized_score_and_held_isolation():
    rng=np.random.default_rng(2026092742);r=rng.standard_t(4,(7,51))*500+1e6
    mask=np.isin(np.arange(51)//5,[0,2,4,5,7,9])
    a,b,_=scores(r,mask);c,d,_=oracle.scores(r,mask)
    np.testing.assert_allclose(a,c,atol=1e-8);np.testing.assert_allclose(b,d,atol=1e-8)
    r[:,~mask]+=1e6;e,_,_=scores(r,mask);np.testing.assert_array_equal(a,e)


def test_saved_real_scalar_comparison():
    import json,hashlib
    here=Path(__file__).resolve().parent
    r=json.loads((here/'fast-real-audit.json').read_text())
    assert r['tracks']==44 and r['candidates']==566
    assert r['fast_sha256']==hashlib.sha256((here/'fast_solver.py').read_bytes()).hexdigest()
    assert r['scalar_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert r['maximum_score_difference']<1e-7
    assert all(v['all_converged'] for v in r['rows'])
