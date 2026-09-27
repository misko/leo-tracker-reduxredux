"""Offline checks for frozen selection, exact joins, and matched evaluation."""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent


def load(name):return json.loads((HERE/name).read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_source_and_whole_scan_selection():
    protocol=load('protocol.json')
    assert protocol['inventory_sha256']==sha(ROOT/'2026_09_27_ds6_roof/approved-inventory.json')
    assert protocol['prior_phase_plan_sha256']==sha(ROOT/'2026_09_27_latest_ten_phase/plan.json')
    old={s['session_id'] for s in json.loads((ROOT/'2026_09_27_latest_ten_phase/plan.json').read_text())['scans']}
    chosen={r['session_id'] for r in protocol['selected']}
    assert len(chosen)==4 and not chosen&old
    assert {r['sample_rate_msps'] for r in protocol['selected']}=={2.5,5.,7.5,10.}
    for name,digest in protocol['source_sha256'].items():assert sha(ROOT/name)==digest
    inventory=json.loads((ROOT/'2026_09_27_ds6_roof/approved-inventory.json').read_text())['captures']
    for record in protocol['selected']:
        pool=[r for r in inventory if r['session_id'] not in old and r['sample_rate_msps']==record['sample_rate_msps'] and r['analysis']=='figures_ready' and r['tracking']=='complete']
        expected=min(pool,key=lambda r:hashlib.sha256(f"{protocol['seed']}:{r['session_id']}".encode()).hexdigest())
        assert record==expected


def test_exact_candidate_joins_and_whole_visit_partitions():
    for record in load('protocol.json')['selected']:
        plan=load(record['session_id']+'-plan.json')
        assert plan['protocol_sha256']==sha(HERE/'protocol.json')
        assert plan['input_manifest_sha256']==record['manifest_sha256']
        tracks={t['track_id']:t for t in plan['tracks']};masks={}
        for track in tracks.values():
            assert len(track['times_s'])==len(track['measured_hz'])==len(track['candidate_ids'])==len(track['visits'])==len(track['training_mask'])
            for v,m in zip(track['visits'],track['training_mask']):assert masks.setdefault(v,m)==m
        used=set()
        for group in plan['selected_groups']:
            vv=[v for v in plan['selected'] if v['group']==group['group']]
            assert sum(v['partition']=='train' for v in vv)==2
            assert sum(v['partition']=='held' for v in vv)==2
            ids={m['rx0_track_id'] for m in vv[0]['modes']}
            assert len(ids)==2 and not used&ids
            used|=ids
        for v in plan['selected']:
            assert (v['partition']=='train')==masks[v['visit']]
            for m in v['modes']:
                t=tracks[m['rx0_track_id']];assert t['receiver_id']==0
                k=t['candidate_ids'].index(m['candidate_ids'][0]);assert t['visits'][k]==v['visit']


def test_complete_accounting_and_identical_matched_support():
    protocol=load('protocol.json')
    for record in protocol['selected']:
        sid=record['session_id'];plan=load(sid+'-plan.json');replay=load(sid+'-replay.json')
        assert replay['complete'] and replay['plan_sha256']==sha(HERE/(sid+'-plan.json'))
        expected={(v['visit'],v['group'],ms) for v in plan['selected'] for ms in protocol['starts_ms']}
        actual=[(r['visit'],r['group'],r['start_ms']) for r in replay['rows']]
        assert len(actual)==len(set(actual)) and set(actual)==expected
        for key in ['controls','audits']:
            assert len(replay[key])==len(plan['selected'])
            assert {(r['visit'],r['group']) for r in replay[key]}=={(v['visit'],v['group']) for v in plan['selected']}
        for row in replay['rows']:
            if row['original']['both_qualified']:
                assert len(row['shared']['held_frame_errors_rad'])==len(row['independent']['held_frame_errors_rad'])
                assert len(set(row['shared']['rates_hz'].values()))==1
            else:assert 'shared' not in row and 'independent' not in row


def test_no_substitution_in_report_and_decision():
    result=load('summary.json');protocol=load('protocol.json')
    assert result['protocol_sha256']==sha(HERE/'protocol.json')
    assert [s['session_id'] for s in result['scans']]==[r['session_id'] for r in protocol['selected']]
    valid=[s for s in result['scans'] if s['evaluable']]
    differences=[s['arms']['shared']['window_mean_mse_rad2']-s['arms']['independent']['window_mean_mse_rad2'] for s in valid]
    assert result['evaluable_scans']==len(valid)
    assert result['improved_scans']==sum(d<0 for d in differences)
    assert result['frozen_decision_passed']==bool(sum(d<0 for d in differences)>=3 and np.mean(differences)<0)


def test_primary_statistic_does_not_weight_by_pilot_count():
    spec=importlib.util.spec_from_file_location('validation_summary',HERE/'summarize.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[]
    # The second window has 100 times as many pilots. The frozen metric gives
    # both windows equal weight; it must not silently become pooled pilot RMS.
    for visit,n,error in [(1,1,1.),(2,100,3.)]:
        result=dict(held_frame_errors_rad=[error]*n,evaluation_dd=.3,train_dd=.2)
        rows.append(dict(visit=visit,group='g',time_s=float(visit),original={'both_qualified':True},shared=result,independent=result))
    plan=dict(session_id='synthetic',rate_hz=1,tracks=[],group_inventory=[],selected_groups=[],selected=[1,2])
    replay=dict(rows=rows,controls=[],audits=[])
    out=module.summarize_scan(plan,replay)
    assert out['arms']['shared']['window_mean_mse_rad2']==5.
    assert out['shared_minus_independent_mse_rad2']==0.
