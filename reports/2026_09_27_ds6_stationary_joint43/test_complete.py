import hashlib
import json
import numpy as np
import pytest
from run_stationary_joint import HERE, REPORTS, digest


def test_frozen_partition_and_inputs():
    p=json.loads((HERE/'protocol.json').read_text());g=p['splits']
    assert len(g['all'])==43
    assert set(g['A']).isdisjoint(g['B'])
    assert set(g['A'])|set(g['B'])==set(g['all'])
    ordered=sorted(g['all'],key=lambda s:hashlib.sha256(f"{p['seed']}:{s}".encode()).hexdigest())
    assert g['A']==ordered[::2] and g['B']==ordered[1::2]
    assert g==json.loads((REPORTS/'2026_09_27_ds6_fresh_joint43/protocol.json').read_text())['splits']
    assert digest(HERE/'run_stationary_joint.py')==p['source_sha256']
    for name,value in p['files'].items():assert digest(REPORTS/name)==value


@pytest.mark.parametrize('name',['all','A','B'])
def test_complete_fits_and_audits(name):
    p=json.loads((HERE/'protocol.json').read_text())
    for name,sessions in [(name,p['splits'][name])]:
        r=json.loads((HERE/f'{name}.json').read_text())
        assert r['complete'] and r['sessions']==sessions
        assert r['protocol_sha256']==digest(HERE/'protocol.json')
        assert len(r['runs'])==2
        assert r['best']==max(r['runs'],key=lambda v:v['train'])
        assert r['best']['success'] and not r['best']['bound_hit']
        assert len(r['best']['x'])==2+len(sessions)
        assert {a['session_id'] for a in r['audits']}==set(sessions)
        for a in r['audits']:
            assert np.isfinite(a['exact_train']) and np.isfinite(a['exact_held'])
            assert a['maximum_interpolation_error_hz']<.05
            assert a['max_offset_gradient']<1e-7


def test_summary_binds_all_results_and_reference():
    s=json.loads((HERE/'summary.json').read_text())
    assert {r['fit'] for r in s['results']}=={'all','A','B'}
    for name,value in s['result_sha256'].items():assert digest(HERE/name)==value
    assert s['reference_sha256']==digest(REPORTS/'2026_09_27_ds6_roof/pose-authority.json')


@pytest.mark.parametrize('name',['all','A','B'])
def test_independent_gradient_audits_at_all_winners(name):
    p=json.loads((HERE/'protocol.json').read_text())
    for name,sessions in [(name,p['splits'][name])]:
        a=json.loads((HERE/f'{name}-gradient.json').read_text())
        assert a['complete'] and a['fit']==name
        assert a['source_sha256']==digest(HERE/'audit_gradient.py')
        assert a['result_sha256']==digest(HERE/f'{name}.json')
        assert [r['session_id'] for r in a['rows']]==sessions
        assert all(r['maximum_difference']<.01 for r in a['rows'])
        assert a['maximum_global_difference']<.01
        assert np.isfinite(a['global_numeric_gradient']).all()
