import json
from run_long import HERE,REPORTS,digest,eligible

def test_complete_fits_use_exact_training_duration_selection():
    p=json.loads((HERE/'protocol.json').read_text());assert len(p['sessions'])==4
    assert digest(HERE/'run_long.py')==p['source_sha256']
    for name,value in p['files'].items():assert digest(REPORTS/name)==value
    for s in p['sessions']:
        r=json.loads((HERE/f'{s}.json').read_text());d=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{s}-plan.json').read_text())
        original=json.loads((REPORTS/'2026_09_27_ds6_element_freshness'/f'{s}.json').read_text())['shortlists']
        expected={t['track_id'] for t in d['tracks'] if t['track_id'] in original and eligible(dict(t=t['times_s'],mask=t['training_mask']),p['minimum_training_span_s'])}
        assert r['complete'] and r['protocol_sha256']==digest(HERE/'protocol.json')
        assert set(r['retained_tracks'])==expected and r['original_track_count']==len(original)
        assert len(r['runs'])==3 and r['best']==max(r['runs'],key=lambda a:a['train'])
        assert r['best']['success']
        assert r['maximum_interpolation_error_hz']<.05 and r['max_offset_gradient']<1e-7
        assert abs(r['exact_all_held']-r['exact_retained_held']-r['exact_omitted_held'])<1e-8

def test_summary_binds_all_results_and_reference():
    p=json.loads((HERE/'protocol.json').read_text());s=json.loads((HERE/'summary.json').read_text())
    assert {r['session_id'] for r in s['results']}==set(p['sessions'])
    for path,value in s['result_sha256'].items():assert digest(HERE/path)==value
    assert s['truth_sha256']==digest(REPORTS/'2026_09_27_ds6_roof/pose-authority.json')
