"""One verified native read; frozen R01/R02 held methods remain separate."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import expansion
import scorer

HERE=Path(__file__).resolve().parent;OUT=HERE/'held'
R01=expansion.R01;INPUT=R01/'held_validation/prediction'
_ENGINES=None
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with (gzip.open(path,'xt') if str(path).endswith('.gz') else Path(path).open('x')) as f:
        json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def engines():
    global _ENGINES
    if _ENGINES is None:_ENGINES=expansion.frozen_modules()+(scorer,)
    return _ENGINES


def score_receiver(samples,rate,edge,r01_prediction,r02_prediction,raw_authority,on_selected):
    if r01_prediction['target_support']!=r02_prediction['target_support']:raise ValueError('method native supports differ')
    if r01_prediction['header']['prediction_id']!=r02_prediction['prediction_id']:raise ValueError('method target IDs differ')
    math,adapter,full=engines();packet=adapter.adapt(r01_prediction,raw_authority)
    began=time.monotonic();one=math.score_target(samples,rate,edge,packet,on_selected);r01_time=time.monotonic()-began
    # Full-window controls are evaluated only after R01 nomination is sealed.
    began=time.monotonic();two=full.score_packet(samples,rate,edge,r02_prediction);r02_time=time.monotonic()-began
    if one['owner_id']!=two['owner_id']:raise ValueError('methods disagree on native RX owner')
    return dict(r01_packet=packet,r01=one,r02=two,r01_scoring_seconds=r01_time,r02_scoring_seconds=r02_time,
        methods_remain_separate=True,best_method_selected=False,shared_verified_raw_samples=True)


def prepare():
    old=read(R01/'timing/protocol.json');two=read(HERE/'protocol.json')
    meta=read(INPUT/'verification.json')
    if not meta['all_passed'] or meta['receiver_cells']!=576:raise ValueError('held metadata audit prerequisite failed')
    split=read(R01/'split.json');panel=read(INPUT/'panel.json')
    if {s['case'] for s in panel['slots']}!=set(split['validation']) or len(panel['slots'])!=288:
        raise ValueError('held split/panel differs')
    files=dict(old['files']);files.update(two['files'])
    paths=[Path(__file__),HERE/'test_held.py',HERE/'scorer.py',HERE/'expansion.py',HERE/'protocol.json',
        HERE/'artifact_seal.json',R01/'timing/protocol.json',R01/'HELD_VALIDATION_PLAN.md']
    paths += [INPUT/n for n in ['protocol.json','handoff_protocol.json','panel.json','r01_prediction_packets.json',
        'r02_predictions.json','r01_forecast_seal.json','r02_forecast_seal.json','verification.json','artifact_seal.json']]
    files.update({str(p):sha(p) for p in paths})
    tests=subprocess.run([sys.executable,'-m','unittest','-v','test_held'],cwd=HERE,capture_output=True,text=True,timeout=60)
    write(OUT/'test_results.json',dict(exit_code=tests.returncode,stdout=tests.stdout,stderr=tests.stderr))
    if tests.returncode:raise ValueError('held application tests failed')
    files[str(OUT/'test_results.json')]=sha(OUT/'test_results.json')
    write(OUT/'protocol.json',dict(schema='frozen-method-held-acquisition-application/v1',frozen_utc_ns=time.time_ns(),files=files,
        panel=str(INPUT/'panel.json'),r01_forecasts=str(INPUT/'r01_prediction_packets.json'),r02_forecasts=str(INPUT/'r02_predictions.json'),
        cases=split['validation'],requested_windows=288,requested_cells=576,maximum_workers=2,process_bound_seconds=580,BLAS_threads=1,
        runtime_identity=old['runtime_identity'],no_union_or_best_method=True,no_recovered_donors=True,
        fresh_per_window_blind_parity=False,global_detector_parity_evidence='R01 unchanged runtime,288development paired replays',
        mandatory_current_native_IQ_index_and_full_reader_exhaustion=True,raw_outcomes_before_freeze=0,requires_root_authorization=True))
    print('held application frozen',sha(OUT/'protocol.json'),flush=True)


def run(case):
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(key)!='1':raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('580second held bound')));signal.alarm(580)
    began=time.monotonic();p=read(OUT/'protocol.json');approval=read(OUT/'run_authorization.json')
    if approval['protocol_sha256']!=sha(OUT/'protocol.json') or not approval['raw_scoring_authorized']:raise ValueError('held stage not authorized')
    if case not in p['cases']:raise ValueError('case outside held split')
    for path,h in p['files'].items():
        if sha(path)!=h:raise ValueError('frozen held source/input changed: '+path)
    from leo.processing.fast_scan import implementation_identity
    code,environment=implementation_identity()
    if (code,environment)!=(p['runtime_identity']['code_digest'],p['runtime_identity']['environment_digest']):raise ValueError('historical runtime changed')
    panel=read(p['panel']);one=read(p['r01_forecasts']);two=read(p['r02_forecasts'])
    r01={r['header']['prediction_id']:r for r in one['rows']};r02={r['prediction_id']:r for r in two['rows']}
    rows=[];track_cache={}
    for slot in [s for s in panel['slots'] if s['case']==case]:
        row=dict(request_id=slot['request_id'],case=case,channel=slot['channel'],status='started',cells=[])
        try:
            if time.monotonic()-began>540:raise TimeoutError('reserve checkpoint budget')
            if slot['status']!='nominated':raise ValueError(slot.get('reason','missing slot'))
            window,ids,values,receipt=expansion.open_native(slot);row['native_receipt']=receipt
            for index,rx in enumerate(ids):
                h=next(c['header'] for c in slot['cells'] if c['header']['receiver_id']==rx);pid=h['prediction_id']
                def selected(value):write(OUT/'selections'/(pid.replace('/','_')+'.json'),value)
                result=score_receiver(values[:,index],window.sample_rate_hz,window.target['edge'],r01[pid],r02[pid],slot['raw_authority'],selected)
                path=slot['tracking']['path']
                if path not in track_cache:track_cache[path]=read(path)
                original=next((probe for probe in track_cache[path]['source']['probes'] if probe['visit_index']==h['visit_index'] and probe['probe_index']==h['probe_index'] and probe['receiver_id']==rx),None)
                row['cells'].append(dict(prediction_id=pid,receiver_id=rx,header=h,result=result,r02_prediction=r02[pid],original_fullwindow=original,
                    original_used_for_evaluation_only=True))
            row['status']='complete'
        except Exception as exc:row.update(status='failed',error=repr(exc))
        rows.append(row);write(OUT/'checkpoints'/(slot['request_id']+'.json.gz'),row)
        print(slot['request_id'],row['status'],flush=True)
    write(OUT/'outcomes'/(case+'.json.gz'),dict(rows=rows,seconds=time.monotonic()-began,protocol_sha256=sha(OUT/'protocol.json'),
        methods_remain_separate=True,no_new_per_window_blind_parity=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);parser.add_argument('--case');a=parser.parse_args()
    prepare() if a.action=='prepare' else run(a.case)
