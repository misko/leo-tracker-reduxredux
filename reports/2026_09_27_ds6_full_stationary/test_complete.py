"""Full dataset completion gate, separate from development preflight tests."""
import json
import numpy as np
from run_full import HERE,REPORTS,digest


def test_all43_stationary_fits_and_exact_audits():
    p=json.loads((HERE/'protocol.json').read_text())
    assert len(set(p['sessions']))==43
    assert p['source_sha256']==digest(HERE/'run_full.py')
    for name,value in p['files'].items():assert digest(REPORTS/name)==value
    for session in p['sessions']:
        r=json.loads((HERE/f'{session}.json').read_text())
        assert r['complete'] and r['protocol_sha256']==digest(HERE/'protocol.json')
        assert len(r['runs'])==3 and r['best']==max(r['runs'],key=lambda v:v['train'])
        assert r['best']['max_offset_gradient']<1e-7
        assert r['maximum_interpolation_error_hz']<.05
        assert r['maximum_gradient_difference']<.01
        assert np.isfinite(r['exact_train']) and np.isfinite(r['exact_held'])


def test_complete_summary_binds_all_results():
    s=json.loads((HERE/'summary.json').read_text());p=json.loads((HERE/'protocol.json').read_text())
    assert s['completed']==s['expected']==43 and s['pending']==0
    assert {r['session_id'] for r in s['results']}==set(p['sessions'])
    for name,value in s['result_sha256'].items():assert digest(HERE/name)==value
    assert s['metrics']['sub_km']==sum(r['stationary_error_m']<1000 for r in s['results'])
