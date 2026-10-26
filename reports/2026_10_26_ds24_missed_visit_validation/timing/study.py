"""Round2 frozen controls/full-window replay; no target-selected method."""
import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import numpy as np
import reader
import scorer

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;PRED=ROOT/'prediction'
R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01')
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encode(x):return x.item() if isinstance(x,np.generic) else x.tolist() if isinstance(x,np.ndarray) else str(x)
def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with (gzip.open(path,'xt') if str(path).endswith('.gz') else Path(path).open('x')) as f:
        json.dump(value,f,indent=2,default=encode,allow_nan=False);f.write('\n')
def runtime_identity():
    from leo.processing.fast_scan import implementation_identity
    code,environment=implementation_identity();return dict(code_digest=code,environment_digest=environment)


def prepare():
    paths=[HERE/n for n in ['PROTOCOL.md','scorer.py','reader.py','study.py','test_scorer.py']]
    paths += [PRED/n for n in ['protocol.json','predictions.json','forecast_seal.json','predictor.py','example_packet.json','INTERFACE.md']]
    paths += [R01/'prediction/panel.json',R01/'timing/protocol.json',R01/'split.json',ROOT/'PLAN.md']
    old=read(R01/'timing/protocol.json');files=dict(old['files'])
    for case in old['development']:paths.append(R01/'timing/outcomes'/(case+'.json.gz'))
    for path,h in files.items():
        if sha(path)!=h:raise ValueError('round1 scientific source changed: '+path)
    files.update({str(p):sha(p) for p in paths})
    test=subprocess.run([sys.executable,'-m','unittest','-v','test_scorer'],cwd=HERE,capture_output=True,text=True,timeout=60)
    write(HERE/'test_results.json',dict(exit_code=test.returncode,stdout=test.stdout,stderr=test.stderr,
        initial_failure='Fixture wrapper expected rows[0]; test corrected before freeze; scorer unchanged'))
    if test.returncode:raise ValueError('owned tests failed')
    files[str(HERE/'test_results.json')]=sha(HERE/'test_results.json')
    write(HERE/'protocol.json',dict(schema='round2-primary-fullwindow-freeze/v2',frozen_utc_ns=time.time_ns(),files=files,
        runtime_identity=runtime_identity(),development=old['development'],methods=list(scorer.METHODS),
        operational_method='quadratic_or_fallback',signal_trials=192,strong_primary_trials=48,strong_stress_trials=48,
        null_trials=128,wrong_signal_trials=32,seeds=dict(signal=2026102610,null=2026102611,wrong=2026102612),
        process_bound_seconds=580,maximum_workers=2,BLAS_threads=1,requested_windows=288,requested_cells=576,
        outcomes_before_freeze=0,IQ_reads_before_freeze=0,requires_root_authorization=True))
    print('frozen',sha(HERE/'protocol.json'),flush=True)


def bound(action):
    for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(k)!='1':raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('580second bound')));signal.alarm(580)
    p=read(HERE/'protocol.json')
    for path,h in p['files'].items():
        if sha(path)!=h:raise ValueError('frozen source/input changed: '+path)
    if runtime_identity()!=p['runtime_identity']:raise ValueError('historical runtime changed')
    approval=read(HERE/'run_authorization.json')
    if approval['protocol_sha256']!=sha(HERE/'protocol.json') or action not in approval['authorized_actions']:
        raise ValueError('stage lacks matching root authorization')
    return p


def generate_wave(edge,cfo_at_midpoint,cfo_rate,timing_rate,timing_acceleration,roll=0):
    from leo.analysis.starlink.templates import qin_edge_pilot_states
    states=qin_edge_pilot_states(edge,symbol_roll=roll);rate=10_000_000
    t=np.arange(200000)/rate;dt=t-.01
    epoch=4321.25+timing_rate*dt+.5*timing_acceleration*dt*dt
    frame_time=np.mod(t-epoch/rate,1/750.);symbol=np.floor(frame_time/4.4e-6).astype(int)
    valid=(symbol>=2)&(symbol<=301);local=frame_time[valid]-symbol[valid]*4.4e-6-2/15*1e-6
    indexes=np.arange(528,536) if edge=='lower' else np.arange(488,496)
    signed=np.where(indexes<512,indexes,indexes-1024);frequencies=(signed-signed.mean())*234375.
    values=np.zeros(200000,complex);active=np.zeros(len(local),complex)
    for tone,frequency in enumerate(frequencies):
        phase=.5*np.pi*(states[symbol[valid]-2,tone].astype(float)+.5)
        active+=np.exp(1j*phase+2j*np.pi*frequency*local)/np.sqrt(8)
    values[valid]=active
    return values*np.exp(2j*np.pi*(cfo_at_midpoint*dt+.5*cfo_rate*dt*dt)+.37j)


def control_packet(owner,edge,rate,error,timing_error,distinct=False):
    start=3540000;stop=3740000;reference=3640000;earlier_reference=100000
    true_mid=213456.75+rate*(reference-earlier_reference)/10_000_000
    point=dict(epoch_samples=4321.25+timing_error,cfo_hz=true_mid+error,cfo_rate_hz_s=rate,
        reference_offset_s=.01,cfo_reference_counter=reference,cfo_half_width_hz=5000.,
        timing_rate_samples_s=100*np.sign(rate),timing_reference_offset_s=.01,
        constant_epoch_approximation=True,maximum_within_window_timing_approximation_samples=1.001)
    methods={name:copy.deepcopy(point) for name in scorer.METHODS}
    if distinct:
        methods['quadratic_or_fallback']['epoch_samples']+=8
        methods['legacy_adapter_linear']['epoch_samples']-=8
    return dict(header=dict(source_id='independent-Gaussian-control/'+owner,receiver_id=0,sample_rate_hz=10_000_000),
        prediction_id=owner,target_support=dict(start_counter=start,stop_counter=stop,generation='synthetic'),
        status='linear_fallback',primary_hypothesis_id='fixed-control-forecast',
        donors=[dict(start_counter=0,stop_counter=200000,reference_counter=earlier_reference,
            CFO_hz=213456.75+error,source_id='synthetic-earlier-measurement')],methods=methods,
        truth_reference_metadata=dict(earlier_reference_counter=earlier_reference,target_reference_counter=reference,
            reference_gap_seconds=(reference-earlier_reference)/10_000_000))


def truth_evaluation(result,truth_mid):
    return {name:dict(cfo_error_hz=item['score']['tracking_cfo_hz']-truth_mid,
        carry_error_hz=item['earlier_prediction_CFO_hz']-truth_mid,
        innovation_hz=item['frequency_innovation_hz'],pilot_confirmed=item['pilot_confirmed'],admitted=item['admitted'])
        for name,item in result['methods'].items() if item['score']['status']=='complete'}


def controls(action):
    began=time.monotonic();p=bound(action);rng=np.random.default_rng(p['seeds'][action]);rows=[];trial=0
    if action=='signal':
        bank=[(edge,db,rate,error,timing_error,False) for edge in ['lower','upper'] for db in [-12,-24]
            for rate in [-2000.,2000.] for error in [-2500.,-750.,-.5*scorer.BIN_HZ,.5*scorer.BIN_HZ,750.,2500.]
            for timing_error in [-3.5,-.5,.5,3.5]]
    else:
        bank=[(edge,None if action=='null' else -12,0.,0.,0.,distinct) for edge in ['lower','upper']
            for distinct in [False,True] for _ in range(32 if action=='null' else 8)]
    for edge,db,rate,error,timing_error,distinct in bank:
        owner=f'{action}/{trial}/{edge}';packet=control_packet(owner,edge,rate,error,timing_error,distinct)
        noise=(rng.normal(size=200000)+1j*rng.normal(size=200000))/np.sqrt(2);values=noise
        truth=213456.75+rate*.354
        if db is not None:
            wave=generate_wave(edge,truth,rate,100*np.sign(rate),8*np.sign(rate),roll=17 if action=='wrong' else 0)
            values=noise+np.sqrt(np.mean(abs(noise)**2)*10**(db/10)/np.mean(abs(wave)**2))*wave
        values=values.astype(np.complex64);result=scorer.score_packet(values,10_000_000,edge,packet)
        row=dict(trial=trial,edge=edge,db=db,true_rate_hz_s=rate,donor_CFO_error_hz=error,timing_error_samples=timing_error,
            distinct_method_points=distinct,target_sha256=hashlib.sha256(values.astype('<c8').tobytes()).hexdigest(),result=result,
            truth_CFO_midpoint_hz=truth,reference_metadata=packet['truth_reference_metadata'],
            evaluation=truth_evaluation(result,truth) if action=='signal' else {})
        rows.append(row);write(HERE/'checkpoints'/f'{action}-{trial}.json.gz',row);trial+=1
    write(HERE/'outcomes'/(action+'.json.gz'),dict(rows=rows,seconds=time.monotonic()-began,
        protocol_sha256=sha(HERE/'protocol.json'),independent_later_vectors=len(rows)))
    print(action,'complete',len(rows),time.monotonic()-began,flush=True)


def recorded(case):
    began=time.monotonic();p=bound('recorded')
    if case not in p['development']:raise ValueError('validation/out-of-panel target forbidden')
    panel=read(R01/'prediction/panel.json');forecast=read(PRED/'predictions.json')
    by_id={r['prediction_id']:r for r in forecast['rows']};prior=read(R01/'timing/outcomes'/(case+'.json.gz'))
    old={r['request_id']:r for r in prior['rows']};rows=[]
    for slot in [s for s in panel['slots'] if s['case']==case]:
        row=dict(request_id=slot['request_id'],case=case,channel=slot['channel'],status='started',cells=[])
        try:
            if time.monotonic()-began>540:raise TimeoutError('reserve checkpoint budget')
            window,ids,values,receipt=reader.open_verified(slot,old[slot['request_id']]);row['native_read_receipt']=receipt
            for index,rx in enumerate(ids):
                pid=f"{slot['request_id']}/RX{rx}";prediction=by_id[pid];score_began=time.monotonic()
                result=scorer.score_packet(values[:,index],window.sample_rate_hz,window.target['edge'],prediction)
                row['cells'].append(dict(prediction_id=pid,receiver_id=rx,prediction=prediction,result=result,
                    scoring_seconds=time.monotonic()-score_began))
            row['status']='complete'
        except Exception as exc:row.update(status='failed',error=repr(exc))
        rows.append(row);write(HERE/'checkpoints'/(slot['request_id']+'.json.gz'),row)
        print(slot['request_id'],row['status'],flush=True)
    write(HERE/'outcomes'/(case+'.json.gz'),dict(rows=rows,seconds=time.monotonic()-began,protocol_sha256=sha(HERE/'protocol.json')))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','signal','null','wrong','recorded']);parser.add_argument('--case');args=parser.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='recorded':recorded(args.case)
    else:controls(args.action)
