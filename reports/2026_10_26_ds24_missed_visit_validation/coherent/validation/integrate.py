"""Audit and stage the exact sealed R01 coherent application, additions only."""
import collections
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
R01=HERE.parent.parent
TIMING=Path('/srv/bulk/leo/research/ds24-missed-visit-r02/timing/expansion_v2')
PRED=R01/'expansion/prediction'
sys.path.insert(0,str(HERE.parent))
from baseline_scope import metadata_inventory,sha
from integration import digest


def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def ordering(result,math,pid):
    receipt=result['selection_receipt'];path=TIMING/'selections'/(pid.replace('/','_')+'.json')
    assert read(path)==receipt
    assert math.digest({k:v for k,v in receipt.items() if k!='selection_sha256'})==receipt['selection_sha256']
    assert receipt['confirmation_accessed'] is False
    assert receipt['point_selected']==result['point']['selected'] and receipt['selected']==result['search']['selected']
    ownership=result['ownership'];intervals=ownership['intervals'];blocks=0;zeros=[]
    for a in intervals:
        for b in intervals:
            if a['group']!=b['group']:assert a['stop']<=b['start'] or b['stop']<=a['start']
    for trial in result['exposure']:
        score=trial['score'];assert -256<=score['offset_samples']<=256
        if score['status']!='complete':continue
        if trial['stage']=='coarse' and score['offset_samples']==0:zeros.append(trial)
        for b in math.geometry(200000,10000000,score['epoch_samples'],ownership,'search'):
            blocks+=1
            assert any(i['group']=='search' and i['start']<=b['sample_start']<b['sample_stop']<=i['stop'] for i in intervals)
    if zeros:assert min(zeros,key=math.rank_key)==result['point']['selected']
    for method in ('point','search'):
        c=result[method]['confirmation']
        if c['status']=='complete':
            for b in math.geometry(200000,10000000,c['epoch_samples'],ownership,'confirmation'):
                assert any(i['group']=='confirmation' and i['start']<=b['sample_start']<b['sample_stop']<=i['stop'] for i in intervals)
    return dict(kind='immutable_source_order_and_durable_callback',selection_sha256=sha(path),
        selection_path=str(path),whole_bank_guard_aware_support_disjoint=True,
        checked_search_block_envelopes=blocks,no_wall_clock_confirmation_start_claim=True)


def stage_row(native,cfo,margin):
    row={k:native[k] for k in ('observation_id','receiver','native_receiver_id','channel','time_s','actual_rf_hz')}
    return dict(row,measured_cfo_hz=cfo,fractional_margin=margin)


def integrate_case(case,document,slots,forecasts,math,adapter):
    tracking,inventory,original=metadata_inventory(case)
    native={(n['native_receiver_id'],n['start_counter']):n for n in inventory}
    old={r['observation_id']:r for r in original};staged=copy.deepcopy(original)
    probes={(p['visit_index'],p['probe_index'],p['receiver_id']):p for p in tracking['source']['probes']}
    expected=[s for s in slots if s['case']==case]
    assert [s['request_id'] for s in expected]==[r['request_id'] for r in document['rows']]
    counts=collections.Counter();seen=set();candidates=[];outcomes=[];packet_checks=0
    for slot,window in zip(expected,document['rows'],strict=True):
        assert window['status']=='complete',window
        receipt=window['native_receipt'];a=slot['raw_authority']
        assert receipt['full_reader_exhausted'] and receipt['native_IQ_sha256']==a['index']['iq_sha256']
        assert receipt['repeated_blind_acquisition_calls']==0 and receipt['fresh_per_window_paired_candidate_parity'] is False
        assert 'not fresh per-window parity' in receipt['detector_parity_reuse']
        assert 'sha256:'+sha(a['index_path'])==a['index_sha256']
        assert {c['receiver_id'] for c in window['cells']}=={c['header']['receiver_id'] for c in slot['cells']}
        counts['paired_windows']+=1
        for cell in window['cells']:
            pid=cell['prediction_id'];packet=cell['packet'];h=packet['header'];result=cell['result']
            assert packet==adapter.adapt(forecasts[pid],a);packet_checks+=1
            n=native[h['receiver_id'],h['start_counter']];oid=n['observation_id']
            assert oid not in seen;seen.add(oid)
            assert h['case']==case and all(h[k]==n[nk] for k,nk in [('channel','channel'),('edge','edge'),('actual_rf_hz','actual_rf_hz'),('sample_rate_hz','sample_rate_hz'),('source_id','recording_id')])
            assert cell['original_fullwindow']==probes[h['visit_index'],h['probe_index'],h['receiver_id']]
            assert result['target_support']==packet['target_support']
            assert result['owner_id']==f"{n['recording_id']}/rx{n['native_receiver_id']}/{n['start_counter']}:{n['stop_counter']}"
            counts['receiver_cells']+=1;counts['status_'+result['status']]+=1
            details=dict(case=case,prediction_id=pid,target_observation_id=oid,block_ids=slot['block_ids'],
                channel=n['channel'],native_receiver_id=n['native_receiver_id'],receiver=n['receiver'],
                time_s=n['time_s'],existing_owner=oid in old,status=result['status'])
            if result['status']!='complete':outcomes.append(details);continue
            order=ordering(result,math,pid)
            for method in ('point','search'):
                counts[method+'_pilot_confirmed']+=result[method]['evaluation']['pilot_confirmed']
                counts[method+'_admitted']+=result[method]['evaluation']['admitted']
            item=result['search'];c=item['confirmation'];selected=item['selected'];mode=result['mode_provenance'][selected['mode_index']]
            pilot=c['status']=='complete' and c['margin']>=.025
            compatible=c['status']=='complete' and abs(c['tracking_cfo_hz']-mode['cfo_hz'])<=mode['cfo_half_width_hz']
            assert item['evaluation']['pilot_confirmed']==pilot and item['evaluation']['continuity_compatible']==compatible
            assert item['evaluation']['admitted']==(pilot and compatible)
            details.update(pilot_confirmed=pilot,admitted=pilot and compatible,
                predicted_cfo_hz=mode['cfo_hz'],measured_cfo_hz=c.get('tracking_cfo_hz'),
                innovation_hz=c.get('tracking_cfo_hz',mode['cfo_hz'])-mode['cfo_hz'],
                earlier_width_hz=mode['cfo_half_width_hz'],ordering_evidence=order)
            if not(pilot and compatible):outcomes.append(details);continue
            if oid in old:
                counts['admitted_existing_preserved']+=1;details['status']='existing_native_owner_preserved';outcomes.append(details);continue
            assert not any(x['passed_fractional_margin_gate'] for x in cell['original_fullwindow']['candidates'])
            assert mode['cfo_reference_counter']==(n['start_counter']+n['stop_counter'])/2
            donors=[]
            for d in mode['donors']:
                dn=native[n['native_receiver_id'],d['support']['start_counter']]
                assert dn['stop_counter']==d['support']['stop_counter']<=n['start_counter']
                assert all(dn[k]==n[k] for k in ('recording_id','stream_generation','raw_authority_digest','channel','edge','actual_rf_hz','sample_rate_hz'))
                assert d['support']['native_generation_verified'] and d['support']['stream_generation']==n['stream_generation']
                donors.append(dict(native_observation_id=dn['observation_id'],candidate_id=d['observation_id'],
                    native_support=d['support'],role='original_history_conditioning_only'))
            staged.append(stage_row(n,c['tracking_cfo_hz'],c['margin']));counts['new_native_additions']+=1
            details.update(status='new_native_exploratory_addition',native=n,donors=donors,
                selected_mode_id=mode['mode_id'],selected_offset_samples=c['offset_samples'],
                confirmation_margin=c['margin'],reference_counter=mode['cfo_reference_counter'],
                donor_count=len(donors),zero_fft_bin=abs(details['innovation_hz'])<1e-7,
                width_exceeds_wrong_pilot_control=mode['cfo_half_width_hz']>4500.,
                uncertainty='existing uncalibrated noise proxy; independent target support does not imply independent fine frequency precision')
            candidates.append(details);outcomes.append(details)
    assert staged[:len(original)]==original and len({o['observation_id'] for o in staged})==len(staged)
    return dict(schema='missed-visit-exploratory-observations-v1',case=case,
        observations=staged,observations_sha256=digest(staged),staged=candidates,
        new_native_detections=len(candidates),corrections=0,additions_only=True,
        scope='original public winners plus this coherent expansion only; no union with earlier sparse additions',
        original_measurements_and_margins_exactly_preserved=True,counts=dict(counts),
        expected_paired_windows=len(expected),expected_receiver_cells=2*len(expected),missing_receiver_cells=0,
        all_target_outcomes=outcomes,packet_reconstructions=packet_checks,
        detector_parity='recording/runtime R01 evidence reused; no fresh blind per-window candidate replay',
        geographic_truth_opened=False,position_execution_authorized=False)


def main():
    began=time.monotonic();p=read(TIMING/'protocol.json');auth=read(TIMING/'run_authorization.json')
    assert auth['raw_scoring_authorized'] and auth['protocol_sha256']==sha(TIMING/'protocol.json')
    for path,h in p['files'].items():assert sha(path)==h,path
    assert p['metadata_handoff_version']==2 and p['no_new_recovered_donors']
    assert read(HERE/'metadata_audit_v2.json')['all_passed']
    assert read(HERE.parent/'signal_control_audit.json')['summary']['-12']['search']['strong_screen_pass']
    assert all(v['search_admitted']['practical_pass'] for v in read(HERE.parent/'null_control_audit.json')['summary'].values())
    math=module('coherent_frozen_R01_math',R01/'timing/timing_search.py')
    adapter=module('coherent_frozen_R01_adapter',R01/'timing/adapter.py')
    slots=read(p['panel_path'])['slots'];forecasts={r['header']['prediction_id']:r for r in read(p['forecast_path'])['rows']}
    summary=[]
    for case in p['cases']:
        path=TIMING/'outcomes'/(case+'.json.gz');document=read(path)
        assert document['protocol_sha256']==sha(TIMING/'protocol.json') and document['fresh_blind_candidate_parity'] is False
        ledger=integrate_case(case,document,slots,forecasts,math,adapter)
        ledger.update(raw_outcome_sha256=sha(path),protocol_sha256=sha(TIMING/'protocol.json'))
        write(HERE/(case+'_additions.json'),ledger)
        prior={r['target_observation_id'] for r in read(HERE.parent/(case+'_additions.json'))['staged']}
        new={r['target_observation_id'] for r in ledger['staged']}
        summary.append(dict(case=case,counts=ledger['counts'],native_added=len(new),
            overlap_sparse_new_ids=sorted(new&prior),new_beyond_sparse=len(new-prior),
            zero_fft_bin=sum(r['zero_fft_bin'] for r in ledger['staged']),
            original_GLRT_count=len(ledger['observations'])-len(new),total_GLRT_count=len(ledger['observations']),
            packet_reconstructions=ledger['packet_reconstructions']))
    write(HERE/'recorded_audit.json',dict(all_passed=True,cases=summary,protocol_sha256=sha(TIMING/'protocol.json'),
        verified_protocol_files=len(p['files']),all526targets_accounted=True,new_raw_reads=0,
        strict_original_plus_expansion_scope=True,geography_used=False,seconds=time.monotonic()-began))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
