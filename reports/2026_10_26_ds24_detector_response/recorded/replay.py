"""Exact bounded original-data replay. Worker writes JSON stdout only."""
import time
STARTED=time.monotonic()
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import sys
import unittest
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
DEPLOYED=Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
REFINER=ROOT/'measurement/refiner.py';REQUESTS=ROOT/'influence/window_requests.json'
FLOATS={'fractional_epoch_offset_samples':1e-9,'fractional_tracking_cfo_hz':1e-6,
        'fractional_exact_score':1e-10,'fractional_control_score':1e-10,'fractional_margin':1e-10}
EXACT=('candidate_rank','integer_epoch_sample','passed_fractional_margin_gate')


def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def encode(x):return x.tolist()if isinstance(x,np.ndarray)else x.item()if isinstance(x,np.generic)else str(x)
def write(p,x):
    with Path(p).open('x')as f:json.dump(x,f,indent=2,default=encode,allow_nan=False);f.write('\n')


def compare(expected,actual):
    checks=[dict(field='candidate_count',passed=len(expected)==len(actual))]
    for i,(old,new)in enumerate(zip(expected,actual)):
        for k in EXACT:checks.append(dict(candidate=i,field=k,passed=old[k]==new[k]))
        for k,tol in FLOATS.items():
            error=abs(float(old[k])-float(new[k]));checks.append(dict(candidate=i,field=k,error=error if math.isfinite(error)else None,
                tolerance=tol,passed=math.isfinite(error)and error<=tol))
    return dict(all_passed=all(c['passed']for c in checks),checks=checks)


def exported(receivers):
    out={}
    for rx in receivers:
        out[rx.receiver_id]=[dict(candidate_rank=c.candidate_rank,integer_epoch_sample=c.epoch_sample,
            **{k:getattr(c,k)for k in FLOATS},passed_fractional_margin_gate=c.fractional_margin>=.025)
            for c in rx.candidates if c.fractional_epoch_status=='complete'and all(getattr(c,k)is not None for k in FLOATS)]
    return out


def fixed_rank(receivers,receiver_id,rank):
    rx=next(x for x in receivers if x.receiver_id==receiver_id)
    found=[c for c in rx.candidates if c.candidate_rank==rank]
    if len(found)!=1:raise ValueError('original requested rank absent/duplicated; no replacement')
    return found[0]


def exhaust_one(source):
    rows=tuple(source.windows())
    if len(rows)!=1:raise ValueError('bounded source did not return exactly one selected window')
    return rows[0]


def runtime_identity():
    from leo.processing.fast_scan import implementation_identity
    from leo.scanner import fast_scan_analysis,fast_scan_detector
    from leo.analysis.starlink import fast_scan_scores,templates
    code,environment=implementation_identity()
    return dict(code_digest=code,environment_digest=environment,
        sources={str(Path(m.__file__)):sha(m.__file__)for m in (fast_scan_analysis,fast_scan_detector,fast_scan_scores,templates)})


def prepare():
    if(HERE/'protocol.json').exists():raise FileExistsError('preserve freeze')
    identity=runtime_identity();requests=load(REQUESTS);authority=load(HERE/'authority.json')
    if len(requests)!=8 or len({r['request_id']for r in requests})!=8:raise ValueError('exact original8 requests required')
    if len({r['complete_owner']for r in requests})!=4:raise ValueError('four complete owners required')
    for r in requests:
        a=r['raw_authority']
        if a['status']!='metadata_ready_IQ_and_detector_parity_unverified':raise ValueError('missing frozen metadata')
        auth=next(v for v in authority['records']if v['case']==r['case'])
        if not auth['identity_matches']or auth['runtime_identity']!=[identity['code_digest'],identity['environment_digest']]:raise ValueError('historical identity mismatch')
        if r['tracking']['sha256']!=sha(r['tracking']['path']):raise ValueError('tracking changed')
        if r['original_candidate']['candidate_rank']<0:raise ValueError('invalid original rank')
    suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_replay.py')
    began=time.monotonic();test=unittest.TextTestRunner(verbosity=2,stream=sys.stderr).run(suite)
    if not test.wasSuccessful():raise RuntimeError('owned tests failed')
    write(HERE/'preparation.json',dict(all_passed=True,tests=test.testsRun,test_seconds=time.monotonic()-began,
        seconds=time.monotonic()-STARTED+2.,earlier_import_allowance_seconds=2.,identity=identity,
        requests=8,owners=4,IQ_reads=0,detector_calls=0))
    paths=[Path(__file__),HERE/'test_replay.py',HERE/'PROTOCOL.md',HERE/'preparation.json',HERE/'authority.json',
        HERE/'authority.py',REQUESTS,ROOT/'influence/RF_seal.json',REFINER,ROOT/'measurement/protocol.json',ROOT/'measurement/RF_seal.json']
    paths += [Path(r['tracking']['path'])for r in requests]
    paths += [DEPLOYED/'leo'/name for name in ('storage/fast_scan.py','storage/short_window.py','storage/uri.py',
        'scanner/fast_scan_analysis.py','scanner/fast_scan_detector.py','analysis/starlink/fast_scan_scores.py',
        'analysis/starlink/fast_scan_fractional.py','analysis/starlink/acquisition.py','analysis/starlink/templates.py','processing/fast_scan.py')]
    write(HERE/'protocol.json',dict(schema='recorded-original8-fixed-rank-refinement/v1',files={str(p):sha(p)for p in sorted(set(paths))},
        request_ids=[r['request_id']for r in requests],maximum_paired_detector_calls=8,cap_cumulative_seconds=180.,
        preparation_seconds=load(HERE/'preparation.json')['seconds'],workers=1,BLAS_threads=1,
        parity_float_tolerances=FLOATS,exact_fields=EXACT,refiner_sha256=sha(REFINER),IQ_during_preparation=False,
        no_graph_satellite_position_GPS=True,no_retry_reselection=True))
    print('FROZEN '+sha(HERE/'protocol.json'),flush=True)


def complete_slots(requests,records,status):
    done={r['request_id']for r in records}
    return records+[dict(request_id=r['request_id'],case=r['case'],role=r['role'],owner=r['complete_owner'],
        status='not_attempted',error=status)for r in requests if r['request_id']not in done]


def worker():
    for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(k)!='1':raise ValueError('BLAS1 required')
    protocol=load(HERE/'protocol.json');approval=load(ROOT/'audit/recorded_preflight.json')
    if not approval['all_passed']or approval['protocol_sha256']!=sha(HERE/'protocol.json'):raise ValueError('exact independent preflight required')
    for p,h in protocol['files'].items():
        if sha(p)!=h:raise ValueError('frozen input/source changed: '+p)
    from leo.storage.fast_scan import FastSegmentSource
    from leo.contracts.fast_scan_native import parse_fast_policy
    from leo.scanner.fast_scan_analysis import analyze_window,production_glrt
    spec=importlib.util.spec_from_file_location('unchanged_measurement_refiner',REFINER)
    refine=importlib.util.module_from_spec(spec);spec.loader.exec_module(refine)
    requests=load(REQUESTS);authority=load(HERE/'authority.json');before=runtime_identity()
    expected_identity=load(HERE/'preparation.json')['identity']
    if before!=expected_identity:raise ValueError('runtime import identity changed')
    records=[];calls=0;status='terminal';deadline=STARTED+180.-protocol['preparation_seconds']
    def alarm(*_):raise TimeoutError('original180second global budget')
    signal.signal(signal.SIGALRM,alarm)
    for request in requests:
        stage='before_read';row=dict(request_id=request['request_id'],case=request['case'],role=request['role'],owner=request['complete_owner'],
            native_observation_id=request['native_observation_id'],time_quantile=request['time_quantile'],status='in_progress')
        began=time.monotonic()
        try:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('budget exhausted before request')
            signal.setitimer(signal.ITIMER_REAL,remaining)
            a=request['raw_authority'];p=request['probe'];auth=next(x for x in authority['records']if x['case']==request['case'])
            if sha(request['source_input']['path'])!=request['source_input']['sha256'].removeprefix('sha256:'):raise ValueError('original source input changed')
            if sha(a['index_path'])!=a['index_sha256'].removeprefix('sha256:'):raise ValueError('declared native index changed')
            source=FastSegmentSource(a['segment'],start_sequence=a['local_sequence'],stop_sequence=a['local_sequence']+1)
            if source.manifest_digest!=a['segment_manifest_sha256']:raise ValueError('segment manifest changed')
            stage='bounded_read_and_exhaust';window=exhaust_one(source)
            if window.iq_sha256!=a['index']['iq_sha256']or window.acquisition!=a['index']['acquisition']or window.target!=a['target']:
                raise ValueError('public raw window differs from frozen metadata')
            if window.sample_rate_hz!=a['sample_rate_hz']or tuple(source.receiver_ids)!=tuple(a['receiver_ids']):raise ValueError('native rate/receivers changed')
            if window.acquisition['sample_start']!=p['window_start_counter']or len(window.samples)!=p['duration_samples']:raise ValueError('physical support changed')
            if window.target['rf_center_hz']-window.target['lnb_lo_hz']-window.acquisition['actual_if_center_hz']!=0:raise ValueError('unhandled nonzero RF calibration center')
            row['full_reader_exhausted']=True;row['IQ_sha256']=window.iq_sha256;row['raw_read_seconds']=time.monotonic()-began
            tracking=load(request['tracking']['path']);expected={q['receiver_id']:q['candidates']for q in tracking['source']['probes']
                if q['visit_index']==p['visit_index']and q['probe_index']==p['probe_index']}
            if set(expected)!=set(source.receiver_ids):raise ValueError('original paired probe membership mismatch')
            if calls>=8:raise RuntimeError('maximum8 paired calls exceeded')
            policy=parse_fast_policy(auth['execution']['pipeline_configuration']['stages']['fast-scan'])
            stage='paired_detector';calls+=1;result=analyze_window(window,source.receiver_ids,None,policy,detector=production_glrt)
            row['full_original_replay_result']=result.model_dump(mode='json')
            if result.status!='processed':raise ValueError('original detector did not process selected window')
            actual=exported(result.receivers);row['candidate_parity']={str(rx):compare(expected[rx],actual.get(rx,[]))for rx in expected}
            if not all(v['all_passed']for v in row['candidate_parity'].values()):raise ValueError('complete paired candidate parity failed')
            stage='fixed_original_rank';peak=fixed_rank(result.receivers,p['receiver_id'],request['original_candidate']['candidate_rank'])
            if not compare([request['original_candidate']],exported([next(r for r in result.receivers if r.receiver_id==p['receiver_id'])])[p['receiver_id']][
                [c['candidate_rank']for c in actual[p['receiver_id']]].index(peak.candidate_rank):][:1])['all_passed']:
                raise ValueError('request original candidate mismatch')
            row['original_replayed_candidate']=peak.model_dump(mode='json')
            if abs(peak.acquired_cfo_hz+peak.fractional_residual_cfo_hz-peak.fractional_tracking_cfo_hz)>1e-7:raise ValueError('acquired/final CFO arithmetic failed')
            stage='continuous_same_cell_refinement';rx_index=source.receiver_ids.index(p['receiver_id'])
            values=window.samples[:,rx_index,0].astype(float)+1j*window.samples[:,rx_index,1].astype(float)
            corrected,correlations=refine.refine(values,window.sample_rate_hz,window.target['edge'],peak.acquired_cfo_hz,peak.epoch_sample,
                peak.fractional_epoch_offset_samples,peak.fractional_residual_cfo_hz,peak.fractional_exact_score,peak.fractional_control_score)
            row.update(status='complete',refinement=corrected,correction_delta_hz=corrected['corrected_tracking_cfo_hz']-peak.fractional_tracking_cfo_hz,
                correlations=dict(exact_values_real=correlations['exact_values'].real,exact_values_imag=correlations['exact_values'].imag,
                    control_values_real=correlations['control_values'].real,control_values_imag=correlations['control_values'].imag,times_s=correlations['times_s']),
                original_rank_and_gate_preserved=True)
        except Exception as exc:
            row.update(status='failed',failed_stage=stage,error=repr(exc));status='stopped_after_error';records.append(row);break
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);row['seconds']=time.monotonic()-began
        records.append(row)
    records=complete_slots(requests,records,status);after=runtime_identity()
    output=dict(schema='recorded-original8-result/v1',protocol_sha256=sha(HERE/'protocol.json'),preflight_sha256=sha(ROOT/'audit/recorded_preflight.json'),
        requests_sha256=sha(REQUESTS),refiner_sha256=sha(REFINER),status=status,records=records,declared_slots=8,
        completed=sum(r['status']=='complete'for r in records),paired_detector_calls=calls,identity_before=before,identity_after=after,
        runtime_identity_unchanged=before==after,cumulative_worker_seconds=time.monotonic()-STARTED+protocol['preparation_seconds'],
        numerical_frequency_qualified=sum(r.get('refinement',{}).get('numerical_frequency_qualified',False)for r in records),
        no_reselection_or_retry=True,no_graph_satellite_position_GPS=True,real_frequency_truth_available=False)
    print(json.dumps(output,indent=2,default=encode,allow_nan=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','worker']);a=parser.parse_args()
    prepare()if a.action=='prepare'else worker()
