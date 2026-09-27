import json
import hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def test_all_four_matched_fits_with_recorded_timing_bounds():
    p=json.loads((HERE/'protocol.json').read_text())
    assert digest(HERE/'run.py')==p['source_sha256']
    for path,value in p['files'].items():assert digest(HERE.parent/path)==value
    assert len(p['sessions'])==4 and len(p['timing_audit'])==43
    timing={r['session_id']:r for r in p['timing_audit']}
    for session in p['sessions']:
        r=json.loads((HERE/f'{session}.json').read_text());t=timing[session]
        assert r['complete'] and r['protocol_sha256']==digest(HERE/'protocol.json')
        assert len(r['runs'])==3 and r['best']==max(r['runs'],key=lambda x:x['train'])
        assert r['best']['success'] and not r['best']['horizontal_bound_hit']
        assert all(t['lower_s']-1e-12<=a['x'][2]<=t['upper_s']+1e-12 for a in r['runs'])
        assert r['maximum_interpolation_error_hz']<.05 and r['max_offset_gradient']<1e-7

def test_summary_binds_every_result_and_reference():
    p=json.loads((HERE/'protocol.json').read_text());s=json.loads((HERE/'summary.json').read_text())
    assert {r['session_id'] for r in s['results']}==set(p['sessions'])
    for path,value in s['result_sha256'].items():assert digest(HERE/path)==value
    assert s['truth_sha256']==digest(HERE.parent/'2026_09_27_ds6_roof/pose-authority.json')
