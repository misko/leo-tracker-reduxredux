import json
from evaluate import corrections
from export import HERE,REPORTS,digest


def test_complete_exports_and_transfer_coverage():
    p=json.loads((HERE/'protocol.json').read_text())
    assert p['source_sha256']==digest(HERE/'export.py')
    for path,value in p['files'].items():assert digest(REPORTS/path)==value
    data={n:json.loads((HERE/f'{n}.json').read_text()) for n in ['A','B']}
    for name,d in data.items():
        assert d['complete'] and d['protocol_sha256']==digest(HERE/'protocol.json')
        assert {r['session_id'] for r in d['tracks']}<=set(p['splits'][name])
        for r in d['tracks']:
            assert r['posterior_mass']>=.95 and r['training_span_s']>=30
            assert len(r['centered_times_s'])==len(r['residual_hz'])==len(r['training_mask'])
    summary=json.loads((HERE/'summary.json').read_text())
    for path,value in summary['source_sha256'].items():assert digest(HERE/path)==value
    for path,value in summary['input_sha256'].items():assert digest(HERE/path)==value
    expected=[]
    for target,donor in [('A','B'),('B','A')]:
        learned=corrections(data[donor]['tracks'])
        expected += [(target,r['track_id']) for r in data[target]['tracks'] if r['norad'] in learned]
    assert [(r['target'],r['track_id']) for r in summary['tracks']]==expected
    assert summary['transferred_tracks']==len(expected)
