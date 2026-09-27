import importlib.util
import hashlib
import json
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('prepare',Path(__file__).with_name('prepare.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_fft_correlation_matches_direct_unknown_response_integration():
    rng=np.random.default_rng(4);a=rng.random(72);a/=a.sum();b=rng.random(72);b/=b.sum();actual=m.correlation(a,b)
    expected=np.array([np.mean(a*72*np.roll(b*72,-k)) for k in range(72)])
    np.testing.assert_allclose(actual,expected,atol=1e-12)
    assert abs(actual.mean()-1)<1e-12


def test_flat_phase_is_uninformative_and_contamination_identity():
    n=72;rng=np.random.default_rng(5);a=rng.random(n);a/=a.sum();b=rng.random(n);b/=b.sum();epsilon=.1
    np.testing.assert_allclose(m.correlation(a,np.ones(n)/n),1,atol=1e-12)
    np.testing.assert_allclose(m.correlation((1-epsilon)*a+epsilon/n,(1-epsilon)*b+epsilon/n),(1-epsilon)**2*m.correlation(a,b)+1-(1-epsilon)**2,atol=1e-12)


def test_real_training_only_phase_and_full_candidate_accounting():
    root=Path(__file__).resolve().parent;inputs=json.loads((root/'inputs.json').read_text());result=json.loads((root/'results.json').read_text());source=json.loads((root.parent/'2026_09_27_ds6_differential_cfo/results.json').read_text());previous=json.loads((root.parent/'2026_09_27_ds6_pair_proposals/full-results.json').read_text())
    assert result['complete'] and result['protocol_sha256']==hashlib.sha256((root/'protocol.json').read_bytes()).hexdigest()
    for scan,prepared,old,full in zip(result['scans'],inputs['scans'],source['scans'],previous['scans']):
        assert scan['session_id']==prepared['session_id']==old['session_id']==full['session_id']
        np.testing.assert_allclose(scan['scores']['cfo_only']['held_cfo_log_predictive'],full['response_only']['cfo_only_held_log_predictive'],rtol=0,atol=1e-9)
        for g,p,o,f in zip(scan['groups'],prepared['groups'],old['groups'],full['groups']):
            assert g['group']==p['group']==o['group']==f['group'];assert g['pair_counts']==f['pair_counts']
            assert {v['visit'] for v in p['observations']}=={v['visit'] for v in o['phase_observations'] if v['train']}
            assert abs(np.mean(p['offset_correlation'])-1)<1e-10
