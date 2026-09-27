import json
import numpy as np
from audit import HERE,REPORTS,digest

def test_all_four_audits_cover_frozen_tracks_and_bind_sources():
    p=json.loads((HERE/'protocol.json').read_text())
    assert p['source_sha256']==digest(HERE/'audit.py') and len(p['sessions'])==4
    for path,value in p['files'].items():assert digest(REPORTS/path)==value
    for s in p['sessions']:
        r=json.loads((HERE/f'{s}.json').read_text());base=json.loads((REPORTS/'2026_09_27_ds6_element_freshness'/f'{s}.json').read_text())
        assert r['complete'] and r['protocol_sha256']==digest(HERE/'protocol.json')
        assert {t['track_id'] for t in r['tracks']}==set(base['shortlists'])
        for key in ['maximum_raw_difference_hz','maximum_shape_difference_hz','maximum_step_halving_difference_hz']:
            assert all(np.isfinite(t[key]) and t[key]>=0 for t in r['tracks'])
            assert r[key]==max(t[key] for t in r['tracks'])
