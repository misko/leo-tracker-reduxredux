"""Bounded estimator evaluation. Truth lives in this harness, never estimator."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import time
import numpy as np
import estimator

HERE=Path(__file__).resolve().parent
PRIOR=Path('/srv/bulk/leo/research/ds24-ch78-diagnosis-r03/detection')
RUNTIME=Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


old=module('frozen_disjoint_detection',PRIOR/'study.py')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def encode(x):return x.tolist() if isinstance(x,np.ndarray) else x.item() if isinstance(x,np.generic) else str(x)
def write(p,value):
    with Path(p).open('x') as f:json.dump(value,f,indent=2,default=encode,allow_nan=False);f.write('\n')


def prepare():
    p=read(PRIOR/'protocol.json')
    for path,digest in p['files'].items():
        if sha(path)!=digest:raise ValueError('inherited source changed: '+path)
    files=dict(p['files'])
    authority=old.old.PRIOR/'recorded/protocol.json'
    for path,digest in read(authority)['files'].items():
        if sha(path)!=digest:raise ValueError('historical reader authority changed: '+path)
        files[path]=digest
    files[str(authority)]=sha(authority)
    for name in ['PROTOCOL.md','estimator.py','test_estimator.py','study.py']:
        files[str(HERE/name)]=sha(HERE/name)
    for name in ['protocol.json','panel.json','recorded.json','RF_seal.json','verification.json']:
        files[str(PRIOR/name)]=sha(PRIOR/name)
    files[str(RUNTIME/'leo/analysis/starlink/fast_scan_fractional.py')]=sha(RUNTIME/'leo/analysis/starlink/fast_scan_fractional.py')
    write(HERE/'protocol.json',dict(schema='frequency-continuity-freeze/v1',files=files,
        frozen_utc_ns=time.time_ns(),runtime_identity=old.old.replay.runtime_identity(),
        IQ_reads_before_freeze=0,new_outcomes_before_freeze=0,
        process_bound_seconds=580,BLAS_threads=1,maximum_workers=2,
        synthetic_seed=5826102601,null_seed=5826102602,signal_trials=288,null_trials=128,
        estimator_version=estimator.VERSION,grid_points=len(estimator.GRID),
        strong_accuracy_threshold=.8,coverage_threshold=.9,evolution_slope_range=[.5,1.5],
        conditional_null_upper95_threshold=.05,no_GPS=True,no_new_RF=True))
    print('frozen',sha(HERE/'protocol.json'),flush=True)


def bounded():
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(key)!='1':raise ValueError('BLAS1 required')
    def timeout(*_):raise TimeoutError('580-second numerical worker bound')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(580)
    p=read(HERE/'protocol.json')
    for path,digest in p['files'].items():
        if sha(path)!=digest:raise ValueError('frozen source changed: '+path)
    if old.old.replay.runtime_identity()!=p['runtime_identity']:raise ValueError('runtime changed')
    return p


def synth_packet(edge,error=0.,rate=0.,dt=.354,extra=False):
    start=3540000; initial=213456.75
    epoch=(4321.25-start)%(10_000_000/750.)
    hypotheses=[]
    for i,offset in enumerate([-1000.,0.,1000.] if extra else [0.]):
        hypotheses.append(dict(hypothesis_id=f'synthetic-donor-{i}',epoch_samples=epoch,
            predicted_cfo_hz=initial+error+rate*dt+offset,prediction_sigma_hz=150.,
            elapsed_s=dt,carry_cfo_hz=initial+error+offset,
            donors=[dict(observation_id=f'synthetic-earlier-{i}',
                support=dict(start_counter=0,stop_counter=100000,generation='synthetic'),
                cfo_hz=initial+error+offset)]))
    return dict(prediction_id='synthetic-'+edge,target_support=dict(start_counter=start,
        stop_counter=start+100000,generation='synthetic',source='independent-later-noise'),hypotheses=hypotheses)


def summarize_evaluation(result,true_cfo):
    primary=result['primary']
    if primary is None:return dict(status='no_donor',accurate=False)
    proposed=primary['proposed']; lo,hi=proposed['conditional_95_interval_hz']
    errors=dict(unchanged=primary['unchanged_later_bin']['tracking_cfo_hz']-true_cfo,
        carry=primary['donor_carry']['cfo_hz']-true_cfo,proposal=proposed['cfo_hz']-true_cfo)
    return dict(errors_hz=errors,accurate={k:bool(abs(v)<=100) for k,v in errors.items()},
        conditional_95_covers=bool(lo<=true_cfo<=hi),gate=primary['passed_gate'],
        proposal_change_from_carry_hz=proposed['cfo_hz']-primary['donor_carry']['cfo_hz'])


def compact(result):
    # Retain full proposal grids in outcomes; no raw complex IQ is written.
    return result


def synthetic():
    began=time.monotonic();p=bounded();rng=np.random.default_rng(p['synthetic_seed']);rows=[]
    for edge in ['lower','upper']:
        for db in [-12,-24]:
            for true_rate in [-2000.,0.,2000.]:
                packet=synth_packet(edge);epoch=packet['hypotheses'][0]['epoch_samples']
                t=np.arange(100000)/10_000_000
                # Earlier-to-target chirp is represented without allocating the gap.
                phase=2*np.pi*((213456.75+true_rate*.354)*t+.5*true_rate*t*t)
                wave=old.old.analytic(100000,10_000_000,edge,epoch=epoch,cfo=0)*np.exp(1j*phase)
                for repetition in range(4):
                    noise=(rng.normal(size=100000)+1j*rng.normal(size=100000))/np.sqrt(2)
                    values,power=old.old.injection(noise,wave,db);values=values.astype(np.complex64)
                    support_hash=hashlib.sha256(values.astype('<c8').tobytes()).hexdigest()
                    # Same target samples compare donor errors and rate predictions.
                    for error in [-500.,0.,500.]:
                        for forecast in ['zero_rate','correct_rate_mechanism']:
                            prediction=synth_packet(edge,error,true_rate if forecast=='correct_rate_mechanism' else 0.)
                            result=estimator.estimate(values,10_000_000,edge,prediction)
                            truth=213456.75+true_rate*(.354+.005)
                            rows.append(dict(edge=edge,db=db,true_rate_hz_s=true_rate,
                                donor_error_hz=error,forecast=forecast,repetition=repetition,
                                target_sha256=support_hash,power=power,estimate=compact(result),
                                evaluation=summarize_evaluation(result,truth),truth_cfo_hz=truth))
        print(edge,'synthetic completed',flush=True)
    write(HERE/'synthetic.json',dict(protocol_sha256=sha(HERE/'protocol.json'),rows=rows,
        seconds=time.monotonic()-began,independent_later_noise_vectors=48,
        conditional_comparisons=len(rows),shared_targets_are_not_independent_trials=True))


def nulls():
    began=time.monotonic();p=bounded();rng=np.random.default_rng(p['null_seed']);rows=[]
    for edge in ['lower','upper']:
        for trial in range(64):
            values=((rng.normal(size=100000)+1j*rng.normal(size=100000))/np.sqrt(2)).astype(np.complex64)
            result=estimator.estimate(values,10_000_000,edge,synth_packet(edge,extra=trial>=32))
            rows.append(dict(edge=edge,trial=trial,proposal_count=len(result['hypotheses']),
                later_sha256=hashlib.sha256(values.astype('<c8').tobytes()).hexdigest(),
                estimate=compact(result),false_confirmation=result['any_passed_gate']))
        print(edge,'null completed',flush=True)
    absent=[]
    for i in range(6):
        packet=synth_packet('lower');packet['hypotheses']=[]
        absent.append(estimator.estimate(np.zeros(100000,complex),10_000_000,'lower',packet))
    write(HERE/'null.json',dict(protocol_sha256=sha(HERE/'protocol.json'),rows=rows,absent=absent,
        seconds=time.monotonic()-began,independent_later_vectors=128))


def recorded():
    began=time.monotonic();bounded();rows=[];previous=read(PRIOR/'recorded.json')
    for slot in read(PRIOR/'panel.json')['slots']:
        item=dict(request_id=slot['request_id'],channel=slot['channel'],status='started',cells=[])
        try:
            window,ids,bg,receipt=old.old.opened(slot);rate=window.sample_rate_hz;edge=window.target['edge']
            wave=old.old.analytic(len(bg),rate,edge)
            prev=next(r for r in previous['rows'] if r['request_id']==slot['request_id'])['scenarios']['strong_weak']
            early=prev['earlier_blind'];target=prev['later_support'];donor_support=prev['earlier_support']
            late=np.column_stack([old.superpose(bg[100000:,i],wave[100000:],-24) for i in range(len(ids))]).astype(np.complex64)
            if hashlib.sha256(late.astype('<c8').tobytes()).hexdigest()!=target['support_sha256']:
                raise ValueError('round3 identical later sample reconstruction failed')
            for i,rx in enumerate(ids):
                candidates=old.donors(early[i]);hyp=[]
                for c in candidates:
                    hyp.append(dict(hypothesis_id='rank-'+str(c['candidate_rank']),
                        epoch_samples=(c['integer_epoch_sample']+c['fractional_epoch_offset_samples']-100000)%(rate/750.),
                        predicted_cfo_hz=c['fractional_tracking_cfo_hz'],prediction_sigma_hz=150.,elapsed_s=.01,
                        carry_cfo_hz=c['fractional_tracking_cfo_hz'],donors=[dict(
                            observation_id=f"{slot['request_id']}/rx{rx}/earlier/rank{c['candidate_rank']}",
                            support=donor_support,cfo_hz=c['fractional_tracking_cfo_hz'])]))
                packet=dict(prediction_id=f"{slot['request_id']}/rx{rx}",target_support=target,hypotheses=hyp)
                result=estimator.estimate(late[:,i],rate,edge,packet)
                prior=prev['outcomes'][i]['guided']
                comparisons=[]
                for new,was in zip(result['hypotheses'],prior['proposals']):
                    comparisons.append(dict(rank=new['hypothesis_id'],
                        exact_score_error=new['unchanged_later_bin']['exact_score']-was['score']['exact_score'],
                        cfo_error=new['unchanged_later_bin']['tracking_cfo_hz']-was['score']['tracking_cfo_hz']))
                equal=(len(result['hypotheses'])==len(prior['proposals']) and
                       all(abs(c['exact_score_error'])<=1e-12 and abs(c['cfo_error'])<=1e-9 for c in comparisons))
                item['cells'].append(dict(receiver_id=rx,edge=edge,estimate=result,
                    evaluation=summarize_evaluation(result,old.old.CFO),
                    donor_truth_evaluation=prev['outcomes'][i]['donor_truth_evaluation'],
                    unchanged_round3_equal=equal,comparisons=comparisons))
            item.update(status='complete',receipt=receipt)
        except Exception as exc:item.update(status='failed',error=repr(exc))
        rows.append(item);print(slot['request_id'],item['status'],flush=True)
    write(HERE/'recorded.json',dict(protocol_sha256=sha(HERE/'protocol.json'),rows=rows,
        seconds=time.monotonic()-began,expected_cells=16))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','synthetic','null','recorded'])
    action=parser.parse_args().action
    dict(prepare=prepare,synthetic=synthetic,null=nulls,recorded=recorded)[action]()
