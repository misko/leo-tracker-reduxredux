"""Lean application of exact R01 ports to RF-nominated coherent blocks."""
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import selection

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
R01=ROOT/'prediction'
VALIDATION=ROOT/'validation'
PLAN=ROOT/'COHERENT_EXPANSION_PLAN.md'
CASES=['DS24-0011','DS24-0097']
MAPPER=Path('/srv/bulk/leo/research/ds24-detector-response-r01/influence/raw_metadata.py')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x')as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result);return result


def ports():
    if str(R01)not in sys.path:sys.path.insert(0,str(R01))
    return dict(predictor=module('sealed_R01_predictor',R01/'predictor.py'),
        panel=module('sealed_R01_panel_helpers',R01/'study.py'),
        handoff=module('sealed_R01_handoff',R01/'handoff.py'),
        native=module('sealed_validator_native_IDs',VALIDATION/'baseline_scope.py'),
        mapper=module('sealed_public_native_index_mapper',MAPPER))


def bound(check=True):
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(key)!='1':raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('580-second process bound')))
    signal.alarm(580)
    if check:
        for path,digest in read(HERE/'protocol.json')['files'].items():
            if sha(path)!=digest:raise ValueError('frozen source changed: '+path)


def prepare():
    began=time.monotonic();bound(False);port=ports();old_panel=read(R01/'panel.json')
    old_seal=read(R01/'artifact_seal.json')
    for name in ['predictor.py','study.py','handoff.py','panel.json']:
        if sha(R01/name)!=old_seal['files'][name]['sha256']:raise ValueError('R01 source changed: '+name)
    source_paths=[PLAN,R01/'predictor.py',R01/'study.py',R01/'handoff.py',R01/'panel.json',
        R01/'artifact_seal.json',R01/'protocol.json',ROOT/'split.json',VALIDATION/'baseline_scope.py',MAPPER,
        ROOT/'timing/adapter.py',ROOT/'timing/timing_search.py',ROOT/'timing/protocol.json']
    source_paths += [HERE/n for n in ['PROTOCOL.md','INTERFACE.md','selection.py','study.py','test_selection.py']]
    files={str(p):sha(p)for p in source_paths};documents={};sources={};blocks=[]
    for case in CASES:
        existing=next(s for s in old_panel['slots']if s['case']==case)
        sources[case]=dict(tracking=existing['tracking'],source_input=existing['source_input'])
        data=read(existing['tracking']['path']);documents[case]=data
        if data['source']['sample_rate_hz']!=10000000 or data['source']['probe_ms']!=20:raise ValueError('unhandled geometry')
        for path in [existing['tracking']['path'],existing['source_input']['path']]:files[str(path)]=sha(path)
        ledger_path=VALIDATION/(case+'_additions.json');graph_path=VALIDATION/(case+'-additions-r01')/'graph_audit.json'
        ledger=read(ledger_path);graph=read(graph_path)
        if graph['new_GPS_or_satellite_identity_used']is not False:raise ValueError('non-RF graph selection authority')
        files[str(ledger_path)]=sha(ledger_path);files[str(graph_path)]=sha(graph_path)
        ranked=selection.lanes(ledger,set(graph['graph']['curved_observation_ids']))
        for lane in ranked[:2]:blocks.append(selection.nominate(lane,data['source']['probes'],data['source']['sample_rate_hz']))
    nominated=selection.deduplicate(blocks);slots=[]
    old_pairs={(s['case'],s['probe_metadata']['visit_index'])for s in old_panel['slots']}
    for item in nominated:
        case=item['case'];probe=item['probe'];data=documents[case];source=data['source'];probes=source['probes']
        slot=dict(request_id=f"{case}-CH{probe['channel']}-V{probe['visit_index']}-EXP",case=case,
            channel=probe['channel'],block_ids=item['block_ids'],status='nominated',
            tracking=sources[case]['tracking'],source_input=sources[case]['source_input'],
            probe_metadata=probe,probe=dict(probe,duration_samples=200000,window_start_counter=probe['valid_start_counter']),
            sample_rate_hz=source['sample_rate_hz'],cells=[],overlaps_original_sparse_panel=(case,probe['visit_index'])in old_pairs)
        try:slot['raw_authority']=port['mapper'].one(port['panel'].request(slot,probe))
        except Exception as exc:slot.update(status='missing',error=repr(exc))
        for rx in [0,1]:
            native_probe=dict(probe,receiver_id=rx)
            native=port['native'].native_row(data,native_probe,[0,1])
            header=dict(prediction_id=f"{slot['request_id']}/RX{rx}",request_id=slot['request_id'],case=case,
                channel=probe['channel'],receiver_id=rx,edge=probe['edge'],sample_rate_hz=source['sample_rate_hz'],
                window_samples=200000,start_counter=probe['valid_start_counter'],stop_counter=probe['valid_start_counter']+200000,
                visit_index=probe['visit_index'],probe_index=probe['probe_index'],generation=source['stream_generation'],
                source_id=source['session_id'],actual_rf_hz=probe['actual_rf_hz'],tracking_sha256=slot['tracking']['sha256'],
                raw_recording_authority_digest=source['raw_recording_authority_digest'],native_observation_id=native['observation_id'])
            same=[p for p in probes if p['channel']==probe['channel']and p['edge']==probe['edge']and p['receiver_id']==rx]
            history=sorted([p for p in same if p['valid_start_counter']+200000<=header['start_counter']and
                0<(header['start_counter']-p['valid_start_counter'])/source['sample_rate_hz']<=port['predictor'].HORIZON_S],
                key=lambda p:p['valid_start_counter'])[-port['predictor'].HISTORY_VISITS:]
            slot['cells'].append(dict(header=header,history=history,
                processed_probe_present=any(p['visit_index']==probe['visit_index']for p in same)))
        slots.append(slot)
    write(HERE/'blocks.json',dict(authoritative_plan_sha256=sha(PLAN),blocks=blocks,
        paired_visits_before_dedup=sum(b['retained_paired_visits']for b in blocks),paired_windows=len(slots)))
    write(HERE/'panel.json',dict(schema='coherent-expansion-native-panel/v1',cases=CASES,slots=slots,
        paired_windows=len(slots),receiver_cells=sum(len(s['cells'])for s in slots),maximum_paired_windows=320,
        overlap_original_sparse_paired_windows=sum(s['overlaps_original_sparse_panel']for s in slots),
        selection='approved RF-only ledger/curved-owner rules; closed24second blocks',raw_IQ_reads=0,
        target_candidate_values_included=False,geography_inputs=False,fresh_per_window_paired_detector_parity=False))
    run=subprocess.run([sys.executable,'-B','-m','unittest','-v','test_selection.py'],cwd=HERE,text=True,capture_output=True,timeout=30)
    if run.returncode:raise RuntimeError(run.stderr)
    write(HERE/'test_results.json',dict(exit_code=run.returncode,expected_tests=3,stdout=run.stdout,stderr=run.stderr))
    for name in ['blocks.json','panel.json','test_results.json']:files[str(HERE/name)]=sha(HERE/name)
    write(HERE/'protocol.json',dict(schema='exact-R01-coherent-expansion-forecast/v1',frozen_utc_ns=time.time_ns(),files=files,
        paired_windows=len(slots),receiver_cells=2*len(slots),blocks=len(blocks),process_bound_seconds=580,BLAS_threads=1,
        exact_R01_predictor_sha256=sha(R01/'predictor.py'),exact_R01_handoff_sha256=sha(R01/'handoff.py'),
        source_history='earlier original tracking only; recovered additions never used as donors',
        raw_IQ_reads=0,new_target_scoring_calls=0,position_or_GPS_inputs=False,preparation_seconds=time.monotonic()-began))
    print('frozen',sha(HERE/'protocol.json'),len(slots),2*len(slots),flush=True)


def generate():
    began=time.monotonic();bound();port=ports();panel=read(HERE/'panel.json');rows=[];history={};slots={}
    for slot in panel['slots']:
        slots[slot['request_id']]=slot
        for cell in slot['cells']:
            h=cell['header'];row=dict(header=h,status='failed')
            for probe in cell['history']:history[h['case'],probe['visit_index']]=probe
            try:row.update(status='complete',forecast=port['predictor'].predict(h,cell['history']))
            except Exception as exc:row['error']=repr(exc)
            rows.append(row)
    write(HERE/'predictions.json',dict(schema='sparse-causal-prediction/v1',protocol_sha256=sha(HERE/'protocol.json'),rows=rows,
        exact_predictor_sha256=sha(R01/'predictor.py'),raw_IQ_reads=0,target_candidate_values_read=False))
    unique={}
    for row in rows:
        for mode in row.get('forecast',{}).get('modes',[]):
            for donor in mode['donors']:unique.setdefault((row['header']['case'],donor['visit_index']),row['header']['request_id'])
    authority=[];lookup={}
    for (case,visit),request_id in sorted(unique.items()):
        item=dict(case=case,visit_index=visit,status='failed')
        try:
            result=port['mapper'].one(port['panel'].request(slots[request_id],history[case,visit]))
            item.update(status='metadata_verified',raw_authority=result);lookup[case,visit]=result
        except Exception as exc:item['error']=repr(exc)
        authority.append(item)
    write(HERE/'donor_authority.json',dict(rows=authority,predictions_sha256=sha(HERE/'predictions.json'),raw_IQ_reads=0))
    packets=[]
    for row in rows:
        slot=slots[row['header']['request_id']]
        if slot['status']=='nominated':packet=port['handoff'].enrich(row,slot,lookup)
        else:packet=dict(row,donor_metadata_status='target_metadata_unavailable')
        packet['block_ids']=slot['block_ids'];packet['overlaps_original_sparse_panel']=slot['overlaps_original_sparse_panel']
        packets.append(packet)
    write(HERE/'prediction_packets.json',dict(schema='sparse-native-prediction-packets/v1',protocol_sha256=sha(HERE/'protocol.json'),
        frozen_predictions_sha256=sha(HERE/'predictions.json'),rows=packets,raw_IQ_reads=0,
        numerical_R01_forecasts_unchanged=True,exact_R01_handoff_sha256=sha(R01/'handoff.py')))
    write(HERE/'forecast_seal.json',dict(protocol_sha256=sha(HERE/'protocol.json'),panel_sha256=sha(HERE/'panel.json'),
        predictions_sha256=sha(HERE/'predictions.json'),packets_sha256=sha(HERE/'prediction_packets.json'),
        donor_authority_sha256=sha(HERE/'donor_authority.json'),paired_windows=panel['paired_windows'],receiver_cells=len(rows),
        target_metadata_statuses=dict(Counter(s['status']for s in panel['slots'])),
        donor_window_statuses=dict(Counter(r['status']for r in authority)),packet_metadata_statuses=dict(Counter(r['donor_metadata_status']for r in packets)),
        forecast_statuses=dict(Counter(r.get('forecast',{}).get('status','failed')for r in rows)),
        raw_IQ_reads=0,scoring_calls=0,seconds=time.monotonic()-began,frozen_utc_ns=time.time_ns()))
    print(json.dumps(read(HERE/'forecast_seal.json')),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','generate']);a=p.parse_args()
    dict(prepare=prepare,generate=generate)[a.action]()
