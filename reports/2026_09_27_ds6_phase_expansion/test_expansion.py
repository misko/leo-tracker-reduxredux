import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent


def test_frozen_selection_and_no_replacements():
    p=json.loads((HERE/'protocol.json').read_text());inventory=json.loads((ROOT/'2026_09_27_ds6_roof/approved-inventory.json').read_text())['captures']
    assert len(p['selected'])==4
    for rate,row in zip([2.5,5.,7.5,10.],p['selected']):
        candidates=[r for r in inventory if r['session_id'] not in p['excluded'] and r['sample_rate_msps']==rate and r['analysis']=='figures_ready' and r['tracking']=='complete']
        assert row==min(candidates,key=lambda r:hashlib.sha256(f"{p['seed']}:{r['session_id']}".encode()).hexdigest())


def test_completed_replay_exact_membership_and_source_bindings():
    p=json.loads((HERE/'protocol.json').read_text());summary=json.loads((HERE/'summary.json').read_text());assert summary['complete']
    for record in p['selected']:
        sid=record['session_id'];planpath=HERE/(sid+'-plan.json');plan=json.loads(planpath.read_text());replay=json.loads((HERE/(sid+'-replay.json')).read_text());frames=json.loads((HERE/(sid+'-frames.json')).read_text())
        assert replay['complete'] and replay['plan_sha256']==hashlib.sha256(planpath.read_bytes()).hexdigest()
        assert plan['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        expected={(v['visit'],v['group'],ms) for v in plan['selected'] for ms in p['starts_ms']};key=lambda w:(w['visit'],w['group'],w['start_ms'])
        assert {key(w) for w in replay['rows']}==expected and len(replay['rows'])==len(expected)
        assert {key(w) for w in frames}=={key(w) for w in replay['rows'] if w['original']['both_qualified']}
        used=set()
        for group in plan['selected_groups']:
            visits=[v for v in plan['selected'] if v['group']==group['group']];assert sum(v['partition']=='train' for v in visits)==sum(v['partition']=='held' for v in visits)==2
            tracks={m['rx0_track_id'] for m in visits[0]['modes']};assert not used&tracks;used|=tracks
