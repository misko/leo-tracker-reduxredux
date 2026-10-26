"""Bounded exact historical replay and unchanged same-cell continuous GLRT64."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from prepare import HERE, PRIOR, DEPLOYED, HISTORICAL_PYTHON, sha, load, write, module, encode

OLD=module('exact_historical_replay',PRIOR/'recorded/replay.py')


def physical_key(request):
    p=request['probe']
    return (request['case'],p['visit_index'],p['probe_index'],p['window_start_counter'])


def verify():
    protocol=load(HERE/'protocol.json')
    for path,digest in protocol['files'].items():
        if sha(path)!=digest:
            raise ValueError('frozen file changed '+path)
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        assert os.environ.get(key)=='1'
    return protocol


def worker(stage,index):
    began=time.monotonic();protocol=verify()
    identity=OLD.runtime_identity()
    prior=load(PRIOR/'recorded/preparation.json')['identity']
    assert identity==prior
    from leo.storage.fast_scan import FastSegmentSource
    from leo.contracts.fast_scan_native import parse_fast_policy
    from leo.scanner.fast_scan_analysis import analyze_window,production_glrt
    import numpy as np
    refiner=module('unchanged_glrt64_refiner',PRIOR/'measurement/refiner.py')
    requests=load(HERE/'requests.json');lookup={r['request_id']:r for r in requests}
    plan=load(HERE/(stage+'_plan.json'));batch=plan['batches'][index]
    authority={r['case']:r for r in load(PRIOR/'recorded/authority.json')['records']}
    max_seconds=plan['worker_seconds'];deadline=began+max_seconds
    calls=0;completed=[];status='complete'
    def timeout(*_):
        raise TimeoutError('frozen per-worker time bound')
    signal.signal(signal.SIGALRM,timeout)
    for ids in batch:
        checkpoint={};where='before_read'
        try:
            left=deadline-time.monotonic()
            if left<=0:
                raise TimeoutError('budget exhausted')
            signal.setitimer(signal.ITIMER_REAL,left)
            first=lookup[ids[0]];a=first['raw_authority']
            assert sha(first['source_input']['path'])==first['source_input']['sha256'].removeprefix('sha256:')
            assert sha(a['index_path'])==a['index_sha256'].removeprefix('sha256:')
            source=FastSegmentSource(a['segment'],start_sequence=a['local_sequence'],stop_sequence=a['local_sequence']+1)
            assert source.manifest_digest==a['segment_manifest_sha256']
            where='public_payload_read';window=OLD.exhaust_one(source)
            assert window.iq_sha256==a['index']['iq_sha256'] and window.acquisition==a['index']['acquisition']
            assert window.target==a['target'] and window.sample_rate_hz==a['sample_rate_hz']
            assert tuple(source.receiver_ids)==tuple(a['receiver_ids'])
            assert window.acquisition['sample_start']==first['probe']['window_start_counter']
            assert len(window.samples)==first['probe']['duration_samples']
            assert window.target['rf_center_hz']-window.target['lnb_lo_hz']-window.acquisition['actual_if_center_hz']==0
            tracking=load(first['tracking']['path'])
            expected={p['receiver_id']:p['candidates'] for p in tracking['source']['probes']
                      if p['visit_index']==first['probe']['visit_index'] and p['probe_index']==first['probe']['probe_index']}
            assert set(expected)==set(source.receiver_ids)
            auth=authority[first['case']]
            assert identity['code_digest']==auth['execution']['code_revision']
            assert identity['environment_digest']==auth['execution']['environment_digest']
            policy=parse_fast_policy(auth['execution']['pipeline_configuration']['stages']['fast-scan'])
            where='paired_historical_detector';calls+=1
            result=analyze_window(window,source.receiver_ids,None,policy,detector=production_glrt)
            checkpoint['full_original_replay_result']=result.model_dump(mode='json')
            assert result.status=='processed'
            actual=OLD.exported(result.receivers)
            parity={str(rx):OLD.compare(expected[rx],actual.get(rx,[])) for rx in expected}
            checkpoint['candidate_parity']=parity
            assert all(p['all_passed'] for p in parity.values())
            where='fixed_original_rank_refinement';records=[]
            for rid in ids:
                request=lookup[rid];peak=OLD.fixed_rank(result.receivers,request['probe']['receiver_id'],request['original_candidate']['candidate_rank'])
                candidate=next(c for c in actual[request['probe']['receiver_id']] if c['candidate_rank']==peak.candidate_rank)
                assert OLD.compare([request['original_candidate']],[candidate])['all_passed']
                rx_index=source.receiver_ids.index(request['probe']['receiver_id'])
                values=window.samples[:,rx_index,0].astype(float)+1j*window.samples[:,rx_index,1].astype(float)
                refined,_=refiner.refine(values,window.sample_rate_hz,window.target['edge'],peak.acquired_cfo_hz,
                    peak.epoch_sample,peak.fractional_epoch_offset_samples,peak.fractional_residual_cfo_hz,peak.fractional_exact_score,peak.fractional_control_score)
                records.append(dict(request_id=rid,status='complete',original_replayed_candidate=peak.model_dump(mode='json'),refinement=refined))
            value=dict(kind='window',physical_key=physical_key(first),request_ids=ids,status='complete',
                       records=records,IQ_sha256=window.iq_sha256,full_reader_exhausted=True,**checkpoint)
            completed.extend(ids)
        except Exception as exc:
            value=dict(kind='window',request_ids=ids,status='failed',failed_stage=where,error=repr(exc),**checkpoint)
            status='stopped_after_error'
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)
        print(json.dumps(value,default=OLD.encode,allow_nan=False),flush=True)
        if status!='complete':
            break
    print(json.dumps(dict(kind='terminal',worker=index,status=status,seconds=time.monotonic()-began,
        calls=calls,completed_request_ids=completed,identity_before=identity,identity_after=OLD.runtime_identity()),default=OLD.encode),flush=True)


def checkpoint_records(stage):
    records={};windows=[];terminals=[]
    for index in range(2):
        path=HERE/f'{stage}_worker{index}.jsonl'
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            try:
                value=json.loads(line)
            except json.JSONDecodeError:
                continue
            if value['kind']=='terminal':
                terminals.append(value);continue
            windows.append(value)
            if value['status']=='complete':
                records.update({r['request_id']:r for r in value['records']})
            else:
                records.update({rid:dict(request_id=rid,status='failed',error=value['error'],failed_stage=value['failed_stage']) for rid in value['request_ids']})
    return records,windows,terminals


def run(stage):
    protocol=verify();requests=load(HERE/'requests.json')
    existing={}
    if stage=='complete':
        initial=load(HERE/'initial_summary.json')
        if not initial['all_passed']:
            raise ValueError('initial archival parity/refinement panel did not qualify')
        existing,_,_=checkpoint_records('initial')
    selected=[r for r in requests if (r['initial_panel'] if stage=='initial' else r['request_id'] not in existing)]
    groups={}
    for request in selected:
        groups.setdefault(physical_key(request),[]).append(request['request_id'])
    ordered=sorted(groups);batches=[[groups[k] for k in ordered[i::2]] for i in range(2)]
    budget=44. if stage=='initial' else min(550.,(1150.-load(HERE/'initial_summary.json')['cumulative_worker_seconds'])/2-2.)
    write(HERE/(stage+'_plan.json'),dict(batches=batches,unique_physical_windows=len(groups),worker_seconds=budget,
        request_count=len(selected),protocol_sha256=sha(HERE/'protocol.json'),frozen_before_payload=True))
    def launch(index):
        command=['sudo','-n','-u','leo','env','PYTHONPATH='+str(DEPLOYED),'PYTHONDONTWRITEBYTECODE=1','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1',
                 HISTORICAL_PYTHON,'-B',str(Path(__file__)),'worker','--stage',stage,'--index',str(index)]
        began=time.monotonic();timeout=False
        with (HERE/f'{stage}_worker{index}.jsonl').open('x') as out,(HERE/f'{stage}_worker{index}.stderr').open('x') as err:
            process=subprocess.Popen(command,stdout=out,stderr=err,start_new_session=True)
            try:
                code=process.wait(timeout=budget+2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);code=process.wait();timeout=True
        return dict(worker=index,returncode=code,seconds=time.monotonic()-began,timed_out=timeout)
    with ThreadPoolExecutor(max_workers=2) as pool:
        processes=list(pool.map(launch,range(2)))
    records,windows,terminals=checkpoint_records(stage)
    passed=all(p['returncode']==0 for p in processes) and len(records)==len(selected) and all(r['status']=='complete' for r in records.values())
    summary=dict(stage=stage,all_passed=passed,processes=processes,terminals=terminals,
        nominal_slots=len(selected),completed_slots=sum(r['status']=='complete' for r in records.values()),
        cumulative_worker_seconds=sum(p['seconds'] for p in processes),paired_detector_calls=len(windows),GPS_used=False)
    write(HERE/(stage+'_summary.json'),summary)
    if stage=='complete' or not passed:
        records={**existing,**records};rows=[]
        for request in requests:
            record=records.get(request['request_id'],dict(status='not_attempted',error='incomplete_or_budget_limited'))
            complete=record['status']=='complete';ref=record.get('refinement',{})
            qualified=complete and ref.get('numerical_frequency_qualified',False)
            original=request['original_observation']['measured_cfo_hz']
            proposed=ref.get('corrected_tracking_cfo_hz')
            rows.append(dict(case=request['case'],complete_owner=request['complete_owner'],role=request['role'],
                native_observation_id=request['native_observation_id'],time_s=request['probe']['time_s'],
                original_cfo_hz=original,corrected_cfo_hz=proposed if qualified else original,
                correction_delta_hz=proposed-original if qualified else 0.,proposed_refined_cfo_hz=proposed,
                numerical_frequency_qualified=bool(qualified),numerical_margin_qualified=bool(complete and ref.get('numerical_margin_qualified',False)),
                payload_and_parity_complete=complete,status=record['status'],fallback_to_original=not qualified,error=record.get('error')))
        corrections=dict(schema='ch8-native-cfo-corrections/v1',rows=rows,total_slots=len(rows),
            coverage_complete=all(r['payload_and_parity_complete'] for r in rows),all_frequency_qualified=all(r['numerical_frequency_qualified'] for r in rows),
            same_vector_both_c_arms=True,no_graph_rewrap=True,GPS_used=False)
        write(HERE/'corrections.json',corrections)
        paths=[HERE/'protocol.json',HERE/'nomination_manifest.json',HERE/'requests.json',HERE/'corrections.json']
        paths += sorted(HERE.glob('*_summary.json'))+sorted(HERE.glob('*_plan.json'))+sorted(HERE.glob('*_worker*.jsonl'))+sorted(HERE.glob('*_worker*.stderr'))
        write(HERE/'RF_seal.json',dict(files={str(p):sha(p) for p in paths},coverage_complete=corrections['coverage_complete'],GPS_used=False))
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('run','worker'))
    parser.add_argument('--stage',choices=('initial','complete'),required=True);parser.add_argument('--index',type=int,choices=(0,1))
    args=parser.parse_args()
    worker(args.stage,args.index) if args.action=='worker' else run(args.stage)
