import json
from run_correlated import HERE,REPORTS,digest

def test_frozen_calibration_excludes_target_subset_and_all_fits_finish():
    p=json.loads((HERE/'protocol.json').read_text())
    assert digest(HERE/'run_correlated.py')==p['source_sha256']
    for path,value in p['files'].items():assert digest(REPORTS/path)==value
    splits=json.loads((REPORTS/'2026_09_27_ds6_stationary_joint43/protocol.json').read_text())['splits']
    for session in p['sessions']:
        c=p['calibration'][session]
        assert session in splits[c['target_subset']] and session not in splits[c['donor_subset']]
        assert c['slope_scale_hz_s']>0
        r=json.loads((HERE/f'{session}.json').read_text())
        assert r['complete'] and r['protocol_sha256']==digest(HERE/'protocol.json')
        assert set(r['arms'])==set(p['arms'])
        for name,a in r['arms'].items():
            assert len(a['runs'])==3 and a['best']==max(a['runs'],key=lambda v:v['train'])
            assert a['best']['success']
            assert a['maximum_interpolation_error_hz']<.05
            assert a['slope_scale_hz_s']==(0. if name=='zero_slope' else c['slope_scale_hz_s'])

def test_summary_binds_results_and_evaluation_reference():
    p=json.loads((HERE/'protocol.json').read_text());s=json.loads((HERE/'summary.json').read_text())
    assert {r['session_id'] for r in s['results']}==set(p['sessions'])
    for path,value in s['result_sha256'].items():assert digest(HERE/path)==value
    assert s['truth_sha256']==digest(REPORTS/'2026_09_27_ds6_roof/pose-authority.json')
