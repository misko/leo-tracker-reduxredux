"""Offline provenance and no-silent-selection checks for descriptive plots."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_selection_and_replay():
    p=json.loads((HERE/'protocol.json').read_text())
    assert sha(HERE/'prepare.py')==p['prepare_sha256']
    assert sha(HERE/'replay.py')==p['replay_sha256']
    for name,digest in p['source_sha256'].items():
        assert sha(ROOT/name)==digest
    candidates=[]
    for path in (ROOT/'2026_09_27_ds6_pair_catalogue').glob('*-plan.json'):
        plan=json.loads(path.read_text())
        for group in plan['eligible_groups']:
            vv=sorted(group['visits'],key=lambda v:v['valid_start_counter'])
            if len(vv)>=20:
                span=(vv[-1]['valid_start_counter']-vv[0]['valid_start_counter'])/plan['rate_hz']
                candidates.append((-span,-len(vv),plan['session_id'],group['group'],vv))
    candidates.sort(key=lambda c:c[:4])
    for actual,expected in zip(p['groups'],candidates[:3]):
        assert (actual['session_id'],actual['group'])==expected[2:4]
        vv=expected[4]
        assert actual['selected_visits']==[vv[round(i*(len(vv)-1)/15)]['visit'] for i in range(16)]
    summary=json.loads((HERE/'summary.json').read_text())
    assert summary['complete'] and summary['protocol_sha256']==sha(HERE/'protocol.json')
    assert len(summary['groups'])==3
    total=0
    for record in p['selected']:
        sid=record['session_id'];plan=json.loads((HERE/f'{sid}-plan.json').read_text())
        assert sha(ROOT/'2026_09_27_ds6_pair_catalogue'/f'{sid}-plan.json')==p['census_plan_sha256'][sid]
        replay=json.loads((HERE/f'{sid}-replay.json').read_text())
        assert replay['complete'] and replay['plan_sha256']==sha(HERE/f'{sid}-plan.json')
        expected={(v['group'],v['visit'],ms) for v in plan['selected'] for ms in p['starts_ms']}
        actual={(r['group'],r['visit'],r['start_ms']) for r in replay['rows']}
        assert actual==expected and len(replay['rows'])==len(expected)
        assert len(replay['controls'])==len(plan['selected'])
        total+=len(plan['selected'])
    assert total==48
    for g in summary['groups']:
        assert len(g['visits'])==16 and g['examined_windows']==96
        assert sum(v['qualified_windows'] for v in g['visits'])==g['qualified_windows']


if __name__=='__main__':
    test_selection_and_replay()
    print('Selection, provenance, complete replay membership and plot coverage passed')
