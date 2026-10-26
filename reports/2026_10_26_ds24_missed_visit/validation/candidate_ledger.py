"""Additions-only natural ledger with audited structural selection ordering.

Version two deliberately accepts no fabricated event timestamps. Immutable
scorer/harness hashes, the actual durable callback artifact, call-order tests
and guard-aware geometry provide the ordering evidence for the frozen run.
"""

import argparse
import collections
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import time

from baseline_scope import metadata_inventory,sha
from integration import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
TIMING=ROOT/'timing'
RUNTIME=Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
sys.path.insert(0,str(RUNTIME))


def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as stream:return json.load(stream)


def write(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def timing_module():
    spec=importlib.util.spec_from_file_location('native_ledger_geometry',TIMING/'timing_search.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def verify_controls():
    strong=read(HERE/'signal_control_audit.json')['summary']['-12']['search']
    nulls=read(HERE/'null_control_audit.json')['summary']
    if not strong['strong_screen_pass'] or not all(s['search_admitted']['practical_pass'] for s in nulls.values()):
        raise ValueError('frozen exploratory search controls do not pass')
    protocol=read(TIMING/'protocol.json')
    for path,digest in protocol['files'].items():assert sha(path)==digest,path
    approval=read(TIMING/'run_authorization.json')
    assert approval['protocol_sha256']==sha(TIMING/'protocol.json')
    assert approval['development_recorded_replay_authorized']
    return protocol


def ordering_and_support(result,timing,selection_tag=None):
    receipt=result['selection_receipt'];owner=result['owner_id']
    path=TIMING/'selections'/((selection_tag or owner).replace('/','_')+'.json')
    assert read(path)==receipt
    assert timing.digest({k:v for k,v in receipt.items() if k!='selection_sha256'})==receipt['selection_sha256']
    assert receipt['point_selected']==result['point']['selected']
    assert receipt['selected']==result['search']['selected']
    assert receipt['confirmation_accessed'] is False
    ownership=result['ownership'];intervals=ownership['intervals'];search_blocks=0
    for a in intervals:
        for b in intervals:
            if a['group']!=b['group']:assert a['stop']<=b['start'] or b['stop']<=a['start']
    zeros=[]
    for trial in result['exposure']:
        score=trial['score']
        assert -256<=score['offset_samples']<=256
        if score['status']!='complete':continue
        if trial['stage']=='coarse' and score['offset_samples']==0:zeros.append(trial)
        blocks=timing.geometry(200000,10000000,score['epoch_samples'],ownership,'search')
        search_blocks+=len(blocks)
        for b in blocks:
            assert any(i['group']=='search' and i['start']<=b['sample_start']<b['sample_stop']<=i['stop'] for i in intervals)
    if zeros:assert min(zeros,key=timing.rank_key)==result['point']['selected']
    for method in ('point','search'):
        item=result.get(method)
        if item is None:continue
        c=item['confirmation']
        if c['status']!='complete':continue
        for b in timing.geometry(200000,10000000,c['epoch_samples'],ownership,'confirmation'):
            assert any(i['group']=='confirmation' and i['start']<=b['sample_start']<b['sample_stop']<=i['stop'] for i in intervals)
    return dict(kind='audited_source_order_and_durable_callback',
        no_wall_clock_confirmation_start_claim=True,
        selection_path=str(path),selection_sha256=sha(path),selection_content_sha256=receipt['selection_sha256'],
        frozen_scorer_sha256=sha(TIMING/'timing_search.py'),frozen_harness_sha256=sha(TIMING/'study.py'),
        boundary_test_source_sha256=sha(HERE/'test_timing_boundary.py'),
        all_search_block_envelopes_verified=search_blocks,whole_bank_support_disjoint=True)


def build_ledger(case,document,timing):
    tracking,inventory,original=metadata_inventory(case)
    original_by_id={r['observation_id']:r for r in original}
    native={(r['native_receiver_id'],r['start_counter']):r for r in inventory}
    staged=copy.deepcopy(original);admissions=[];observed=[];counts=collections.Counter();seen=set()
    for window in document['rows']:
        counts['windows_'+window['status']]+=1
        parity=window.get('public_source_parity')
        if parity is None:
            observed.append(dict(request_id=window['request_id'],status='source_or_replay_failure',error=window.get('error')))
            continue
        assert parity['full_reader_exhausted'] and all(v['all_passed'] for v in parity['parity'].values())
        for cell in window['cells']:
            result=cell['result'];packet=cell['packet'];h=packet['header'];counts['receiver_cells_seen']+=1
            assert h['case']==case
            n=native[h['receiver_id'],h['start_counter']];oid=n['observation_id']
            assert oid not in seen;seen.add(oid)
            assert all(n[k]==h[key] for k,key in [('channel','channel'),('edge','edge'),('actual_rf_hz','actual_rf_hz'),
                ('sample_rate_hz','sample_rate_hz'),('recording_id','source_id')])
            assert packet['target_support']['stream_generation']==n['stream_generation']
            assert result['owner_id']==f"{n['recording_id']}/rx{n['native_receiver_id']}/{n['start_counter']}:{n['stop_counter']}"
            details=dict(prediction_id=cell['prediction_id'],target_observation_id=oid,
                channel=n['channel'],receiver=n['receiver'],native_receiver_id=n['native_receiver_id'],
                existing_owner=oid in original_by_id,result_status=result['status'])
            if result['status']!='complete':
                details['status']='no_available_search';observed.append(details);continue
            # Recorded callbacks use prediction_id as their durable filename;
            # the receipt itself retains and verifies the stable raw owner.
            order=ordering_and_support(result,timing,cell['prediction_id'])
            for method in ('point','search'):
                item=result.get(method)
                if item:
                    counts[method+'_pilot_confirmed']+=item['evaluation']['pilot_confirmed']
                    counts[method+'_admitted']+=item['evaluation']['admitted']
            item=result['search'];c=item['confirmation'];selected=item['selected'];mode=result['mode_provenance'][selected['mode_index']]
            pilot=c['status']=='complete' and c['margin']>=.025
            compatible=c['status']=='complete' and abs(c['tracking_cfo_hz']-mode['cfo_hz'])<=mode['cfo_half_width_hz']
            assert item['evaluation']['pilot_confirmed']==pilot
            assert item['evaluation']['continuity_compatible']==compatible
            assert item['evaluation']['admitted']==(pilot and compatible)
            details.update(pilot_confirmed=pilot,earlier_frequency_compatible=compatible,
                admitted=pilot and compatible,confirmation_cfo_hz=c.get('tracking_cfo_hz'),
                earlier_width_hz=mode['cfo_half_width_hz'],ordering_evidence=order)
            if pilot and not compatible:
                details['status']='far_CFO_pilot_discovery_unresolved';observed.append(details);continue
            if not(pilot and compatible):
                details['status']='confirmation_or_continuity_failed';observed.append(details);continue
            if oid in original_by_id:
                counts['admitted_existing_preserved']+=1
                details['status']='existing_native_owner_preserved'
                details['confirmation_minus_original_CFO_hz']=c['tracking_cfo_hz']-original_by_id[oid]['measured_cfo_hz']
                observed.append(details);continue
            assert not any(a['passed_fractional_margin_gate'] for a in cell['original_fullwindow'].get('candidates',[]))
            assert mode['cfo_reference_counter']==(n['start_counter']+n['stop_counter'])/2
            donors=[]
            for d in mode['donors']:
                dn=native[n['native_receiver_id'],d['support']['start_counter']]
                assert dn['stop_counter']==d['support']['stop_counter']<=n['start_counter']
                assert all(dn[k]==n[k] for k in ('recording_id','stream_generation','raw_authority_digest','channel','edge','actual_rf_hz','sample_rate_hz'))
                assert d['support']['native_generation_verified']
                assert d['support']['stream_generation']==n['stream_generation']
                donors.append(dict(native_observation_id=dn['observation_id'],candidate_id=d['observation_id'],
                    native_support=d['support'],role='conditioning_only'))
            row={k:n[k] for k in ('observation_id','receiver','native_receiver_id','channel','time_s','actual_rf_hz')}
            row.update(measured_cfo_hz=c['tracking_cfo_hz'],fractional_margin=c['margin'])
            staged.append(row);counts['new_native_additions']+=1
            details.update(status='new_native_exploratory_addition',kind='new_native_detection',
                native=n,measurement_source='unchanged_later_sample_confirmation',
                reference_counter=mode['cfo_reference_counter'],donors=donors,
                selected_mode_id=mode['mode_id'],selected_offset_samples=c['offset_samples'],
                confirmation_margin=c['margin'],proposal_count=len(result['exposure']),
                width_exceeds_wrong_pilot_control=mode['cfo_half_width_hz']>4500.,
                uncertainty='existing uncalibrated radio-noise proxy; no posterior re-use',
                qualified_promotion=False)
            admissions.append(details);observed.append(details)
    assert len({o['observation_id'] for o in staged})==len(staged)
    assert staged[:len(original)]==original
    return dict(schema='missed-visit-exploratory-observations-v1',case=case,
        status='baseline_unchanged' if not admissions else 'RF_additions_staged_pending_fresh_causal_graph',
        observations=staged,observations_sha256=digest(staged),staged=admissions,
        corrections=0,new_native_detections=len(admissions),additions_only=True,
        original_measurements_and_margins_exactly_preserved=True,
        counts=dict(counts),all_target_outcomes=observed,
        expected_paired_windows=24,expected_receiver_cells=48,
        missing_receiver_cells=48-counts['receiver_cells_seen'],
        measurement_qualification='practical-control-passing exploratory ledger; natural sequence/association still pending',
        full_timing_phase_coverage_qualified=False,geographic_truth_opened=False,
        old_bank_reuse_authorized=False,position_execution_authorized=False,
        ordering_policy='audited immutable source order plus durable pre-confirmation callback; no invented wall-clock events')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',required=True);args=parser.parse_args()
    began=time.monotonic();split=read(ROOT/'split.json')
    if args.case not in split['development']:raise ValueError('only frozen development cases are permitted')
    verify_controls();timing=timing_module()
    path=TIMING/'outcomes'/(args.case+'.json.gz');document=read(path)
    assert document['protocol_sha256']==sha(TIMING/'protocol.json')
    result=build_ledger(args.case,document,timing)
    result.update(raw_outcome_sha256=sha(path),protocol_sha256=sha(TIMING/'protocol.json'),seconds=time.monotonic()-began)
    write(HERE/(args.case+'_additions.json'),result)
    print(json.dumps(dict(case=args.case,counts=result['counts'],new_native=result['new_native_detections'],
        corrections=0,seconds=result['seconds'])))


if __name__=='__main__':main()
