import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def test_selection_frozen_from_training_entropy():
    p=json.loads((HERE/'protocol.json').read_text());r=json.loads((HERE/'ranking.json').read_text());assert r['complete'] and p['ranking_sha256']==sha(HERE/'ranking.json')
    assert r['parent_sha256']==sha(ROOT/'2026_09_27_ds6_envelope_refit/all-cfo_only.json')
    scores={s['session_id']:max([t['entropy_nats'] for t in s['tracks'] if t['training_visits']>=2 and t['held_visits']>=2],default=0) for s in r['scans']}
    inv=json.loads((ROOT/'2026_09_27_ds6_roof/approved-inventory.json').read_text())['captures'];pool=[s for s in inv if s['session_id'] not in p['excluded'] and s['analysis']=='figures_ready' and s['tracking']=='complete' and scores[s['session_id']]>=.05]
    assert p['selected']==sorted(pool,key=lambda s:(-scores[s['session_id']],s['session_id']))[:4]


def test_exact_membership_partitions_controls_and_no_replacements():
    p=json.loads((HERE/'protocol.json').read_text());summary=json.loads((HERE/'summary.json').read_text());assert [s['session_id'] for s in summary['scans']]==[s['session_id'] for s in p['selected']]
    for record in p['selected']:
        sid=record['session_id'];planpath=HERE/f'{sid}-plan.json';plan=json.loads(planpath.read_text());r=json.loads((HERE/f'{sid}-replay.json').read_text());assert plan['protocol_sha256']==sha(HERE/'protocol.json') and r['plan_sha256']==sha(planpath) and r['complete']
        assert len(plan['selected_groups'])<=1 and len(plan['selected']) in [0,4]
        tracks={t['track_id']:t for t in plan['tracks']}
        for v in plan['selected']:
            for mode in v['modes']:
                t=tracks[mode['rx0_track_id']];assert t['training_mask'][t['visits'].index(v['visit'])]==(v['partition']=='train')
        assert len(r['rows'])==6*len(plan['selected'])
        assert len(r['controls'])==len(plan['selected'])
        assert all(not c['both_qualified'] for c in r['controls'])
