"""Sealed bounded controls and development replay; no validation outcomes."""
import argparse
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
import adapter
import timing_search as timing

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;PRED=ROOT/'prediction'
PRIOR=Path('/srv/bulk/leo/research/ds24-ch78-diagnosis-r02/detection')
RUNTIME=Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
def read(p):
    with (gzip.open(p,'rt') if str(p).endswith('.gz') else Path(p).open()) as f:return json.load(f)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def encode(x):return x.item() if isinstance(x,np.generic) else x.tolist() if isinstance(x,np.ndarray) else str(x)
def write(p,value):
    Path(p).parent.mkdir(exist_ok=True,parents=True)
    with (gzip.open(p,'xt') if str(p).endswith('.gz') else Path(p).open('x')) as f:
        json.dump(value,f,indent=2,default=encode,allow_nan=False);f.write('\n')
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
old=module('unchanged_historical_reader',PRIOR/'study.py')


def bound(require_approval=True):
    for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(k)!='1':raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('580second process bound')))
    signal.alarm(580)
    p=read(HERE/'protocol.json')
    for path,h in p['files'].items():
        if sha(path)!=h:raise ValueError('frozen dependency changed: '+path)
    if old.replay.runtime_identity()!=p['runtime_identity']:raise ValueError('historical runtime changed')
    if require_approval:
        a=read(HERE/'run_authorization.json')
        if a['protocol_sha256']!=sha(HERE/'protocol.json'):raise ValueError('root authorization does not bind this freeze')
    return p


def prepare():
    began=time.monotonic()
    split=read(ROOT/'split.json')
    paths=[HERE/n for n in ['PROTOCOL.md','timing_search.py','adapter.py','study.py','test_timing_search.py']]
    paths += [ROOT/'split.json',ROOT/'PLAN.md',ROOT/'validation/PROTOCOL.md']
    paths += [PRED/n for n in ['protocol.json','panel.json','predictions.json','prediction_packets.json',
        'predictor.py','example_packet.json','evaluation_targets.json','donor_authority.json','handoff_protocol.json']]
    if (HERE/'protocol_pre_final_v1.json').exists():paths.append(HERE/'protocol_pre_final_v1.json')
    runtime_paths=['analysis/starlink/templates.py','analysis/starlink/fast_scan_scores.py',
        'analysis/starlink/fast_scan_fractional.py','storage/fast_scan.py','storage/short_window.py',
        'storage/uri.py','scanner/fast_scan_analysis.py','scanner/fast_scan_detector.py','processing/fast_scan.py']
    paths += [RUNTIME/'leo'/n for n in runtime_paths]
    paths += [PRIOR/'study.py',old.PRIOR/'recorded/replay.py',old.PRIOR/'recorded/protocol.json']
    inherited=read(old.PRIOR/'recorded/protocol.json')['files']
    for path,h in inherited.items():
        if sha(path)!=h:raise ValueError('inherited historical authority changed')
    files=dict(inherited)
    files.update(read(PRED/'protocol.json')['files'])
    files.update({str(p):sha(p) for p in paths})
    rows=read(PRED/'prediction_packets.json')['rows']
    if len(rows)!=576 or any(r['header']['case'] not in split['development'] for r in rows):
        raise ValueError('development-only complete panel required')
    counts={case:sum(len(r.get('forecast',{}).get('modes',[])) for r in rows if r['header']['case']==case)
        for case in split['development']}
    # Math tests are not outcome controls; save their exact receipt before seal.
    test=subprocess.run([sys.executable,'-m','unittest','-v','test_timing_search'],cwd=HERE,
        capture_output=True,text=True,timeout=60)
    test_receipt=HERE/('test_results_final.json' if (HERE/'test_results.json').exists() else 'test_results.json')
    write(test_receipt,dict(exit_code=test.returncode,stdout=test.stdout,stderr=test.stderr))
    if test.returncode:raise ValueError('owned math tests failed')
    files[str(test_receipt)]=sha(test_receipt)
    write(HERE/'protocol.json',dict(schema='missed-visit-timing-freeze/v1',frozen_utc_ns=time.time_ns(),
        files=files,runtime_identity=old.replay.runtime_identity(),development=split['development'],
        prediction_mode_counts_by_case=counts,requested_cells=576,requested_windows=288,
        signal_trials=240,strong_in_domain_trials=80,out_of_domain_trials=32,wrong_signal_trials=32,
        null_trials=128,null_per_edge_exposure=32,IQ_reads_before_freeze=0,outcomes_before_freeze=0,
        process_bound_seconds=580,maximum_workers=2,BLAS_threads=1,
        preparation_seconds=time.monotonic()-began,requires_root_approval=True,
        pre_outcome_amendment='Added complete raw checkpoints and ownership handoff dependencies; preserved prefinal freeze' if (HERE/'protocol_pre_final_v1.json').exists() else None))
    print('frozen',sha(HERE/'protocol.json'),'mode counts',counts,flush=True)


def synth_packet(owner,edge,error,offset,true_rate,forecast,count=1):
    start=3540000;mid=.01
    known_rate=true_rate if forecast=='rate_propagated' else 0.
    timing_rate=100*np.sign(true_rate) if forecast=='rate_propagated' else 0.
    modes=[]
    for i in range(count):
        modes.append(dict(mode_id=f'{owner}/m{i}',status='mechanism_rate' if known_rate else 'one_donor_fallback',
            epoch_samples=(4321.25-offset+timing_rate*mid+i*1300.)%(10_000_000/750.),
            cfo_hz=213456.75+error+known_rate*(.354+mid)+i*3000.,
            cfo_rate_hz_s=known_rate,reference_offset_s=mid,cfo_half_width_hz=4500.,
            timing_half_width_samples=256.,timing_rate_samples_s=timing_rate,
            donors=[dict(observation_id=f'synthetic-earlier/{i}',support=dict(start_counter=0,stop_counter=200000),
                cfo_hz=213456.75+error+i*3000.)]))
    return dict(owner_id=owner,target_support=dict(start_counter=start,stop_counter=start+200000,
        source_id='independent-complex-Gaussian',generation='synthetic'),modes=modes,edge=edge)


def wave(size,rate,edge,epoch,cfo,cfo_rate,timing_rate,roll=0):
    from leo.analysis.starlink.templates import qin_edge_pilot_states
    states=qin_edge_pilot_states(edge,symbol_roll=roll)
    indexes=np.arange(528,536) if edge=='lower' else np.arange(488,496)
    signed=np.where(indexes<512,indexes,indexes-1024);freq=(signed-signed.mean())*234375.
    t=np.arange(size)/rate;frame_time=np.mod(t*(1-timing_rate/rate)-epoch/rate,1/750.)
    symbol=np.floor(frame_time/4.4e-6).astype(int);valid=(symbol>=2)&(symbol<=301)
    local=frame_time[valid]-symbol[valid]*4.4e-6-2/15*1e-6;out=np.zeros(size,complex)
    active=np.zeros(len(local),complex)
    for tone,f in enumerate(freq):
        phase=.5*np.pi*(states[symbol[valid]-2,tone].astype(float)+.5)
        active+=np.exp(1j*phase+2j*np.pi*f*local)/np.sqrt(8)
    out[valid]=active
    return out*np.exp(2j*np.pi*(cfo*t+.5*cfo_rate*t*t)+.37j)


def selection_writer(tag):
    def save(receipt):write(HERE/'selections'/f'{tag}.json',receipt)
    return save


def evaluate(result,true_cfo,true_epoch,rate):
    out={}
    for name in ['point','search']:
        item=result.get(name)
        if not item or item['confirmation']['status']!='complete':out[name]=dict(available=False);continue
        c=item['confirmation'];error=c['tracking_cfo_hz']-true_cfo
        terr=(c['epoch_samples']-true_epoch+rate/1500)%(rate/750)-rate/1500
        out[name]=dict(available=True,cfo_error_hz=error,timing_error_samples=terr,
            accurate100=bool(abs(error)<=100),accurate500=bool(abs(error)<=500),
            correct_timing=bool(abs(terr)<=2),**item['evaluation'])
    return out


def controls(kind):
    began=time.monotonic();bound();rng=np.random.default_rng(2026102604 if kind=='signal' else 2026102607);rows=[];trial=0
    # Every row receives independent later noise; no repeated-target pseudo N.
    for edge in ['lower','upper']:
        for db in [-12,-18,-24] if kind=='signal' else [-12]:
            offsets=[-256,-97,0,97,256] if kind=='signal' else [-280,280] if kind=='boundary' else [0]
            for offset in offsets:
                for true_rate in [-2000.,2000.]:
                    for error in [-200.,200.]:
                        for forecast in ['zero_rate_fallback','rate_propagated']:
                            count=1
                            owner=f'{kind}/{trial}/{edge}';packet=synth_packet(owner,edge,error,offset,true_rate,forecast,count)
                            noise=(rng.normal(size=200000)+1j*rng.normal(size=200000))/np.sqrt(2)
                            w=wave(200000,10_000_000,edge,4321.25,213456.75+true_rate*.354,true_rate,100*np.sign(true_rate))
                            amplitude=np.sqrt(np.mean(abs(noise)**2)*10**(db/10)/np.mean(abs(w)**2))
                            samples=(noise+amplitude*w).astype(np.complex64)
                            result=timing.score_target(samples,10_000_000,edge,packet,selection_writer(owner.replace('/','_')))
                            rows.append(dict(trial=trial,edge=edge,db=db,timing_offset_samples=offset,
                                true_rate_hz_s=true_rate,donor_error_hz=error,forecast=forecast,
                                target_sha256=hashlib.sha256(samples.astype('<c8').tobytes()).hexdigest(),result=result,
                                evaluation=evaluate(result,213456.75+true_rate*(.354+.01),4321.25+np.sign(true_rate),10_000_000)))
                            trial+=1
        print(kind,edge,'complete',len(rows),flush=True)
    write(HERE/'outcomes'/f'{kind}.json.gz',dict(rows=rows,seconds=time.monotonic()-began,
        protocol_sha256=sha(HERE/'protocol.json'),independent_later_vectors=len(rows)))


def nulls(wrong=False):
    began=time.monotonic();bound();rng=np.random.default_rng(2026102605 if not wrong else 2026102606);rows=[]
    for edge in ['lower','upper']:
        for count in [1,8]:
            for trial in range(8 if wrong else 32):
                owner=f'{"wrong" if wrong else "null"}/{edge}/{count}/{trial}'
                packet=synth_packet(owner,edge,0,0,0,'zero_rate_fallback',count)
                samples=(rng.normal(size=200000)+1j*rng.normal(size=200000))/np.sqrt(2)
                if wrong:
                    w=wave(200000,10_000_000,edge,4321.25,213456.75,0,0,roll=17)
                    samples+=np.sqrt(np.mean(abs(samples)**2)*10**(-12/10)/np.mean(abs(w)**2))*w
                samples=samples.astype(np.complex64)
                result=timing.score_target(samples,10_000_000,edge,packet,selection_writer(owner.replace('/','_')))
                rows.append(dict(edge=edge,modes=count,trial=trial,
                    target_sha256=hashlib.sha256(samples.astype('<c8').tobytes()).hexdigest(),result=result))
            print('wrong' if wrong else 'null',edge,count,'complete',flush=True)
    write(HERE/'outcomes'/('wrong.json.gz' if wrong else 'null.json.gz'),dict(rows=rows,
        seconds=time.monotonic()-began,protocol_sha256=sha(HERE/'protocol.json'),independent_later_vectors=len(rows)))


def oracle(samples,rate,edge,packet,original):
    from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
    candidates=sorted([c for c in original.get('candidates',[]) if c['passed_fractional_margin_gate']],key=lambda c:c['candidate_rank'])
    if not candidates:return dict(status='no_original_gatepass')
    c=candidates[0];ep=c['integer_epoch_sample']+c['fractional_epoch_offset_samples']
    mode=dict(epoch_samples=ep,cfo_hz=c['fractional_tracking_cfo_hz'],cfo_rate_hz_s=0.,reference_offset_s=.01)
    ownership=timing.partition(len(samples),rate,packet['modes'][0]['epoch_samples'] if packet['modes'] else 0.,packet['owner_id'])
    groups={g:timing.scores(samples,rate,edge,mode,[0],ownership,g)[0] for g in ['all','search','confirmation']}
    public=conditioned_glrt64_score(samples,rate,epoch_sample=int(ep),fractional_epoch_offset_samples=ep-int(ep),acquired_cfo_hz=mode['cfo_hz'],edge=edge)
    parity=(abs(groups['all']['margin']-public.margin)<=1e-10 and abs(groups['all']['tracking_cfo_hz']-public.tracking_cfo_hz)<=1e-5)
    return dict(status='complete',evaluation_only=True,candidate_rank=c['candidate_rank'],
        source_epoch_samples=ep,source_cfo_hz=mode['cfo_hz'],groups=groups,public_all_frame_parity=parity,
        never_used_for_operational_nomination=True)


def recorded(case):
    began=time.monotonic();p=bound()
    if case not in p['development']:raise ValueError('validation or unlisted case forbidden')
    panel=read(PRED/'panel.json');predictions=read(PRED/'prediction_packets.json')['rows']
    by_id={r['header']['prediction_id']:r for r in predictions}
    targets={r['prediction_id']:r['target_original'] for r in read(PRED/'evaluation_targets.json')['rows']}
    rows=[]
    for slot in [s for s in panel['slots'] if s['case']==case]:
        row=dict(request_id=slot['request_id'],case=case,channel=slot['channel'],status='started',cells=[])
        try:
            if time.monotonic()-began>540:raise TimeoutError('reserve final checkpoint budget')
            if slot['status']!='nominated':raise ValueError(slot.get('reason','not nominated'))
            legacy=dict(slot,probe=dict(slot['probe_metadata'],duration_samples=200000,
                window_start_counter=slot['probe_metadata']['valid_start_counter']))
            window,ids,bg,receipt=old.opened(legacy);row['public_source_parity']=receipt
            for index,rx in enumerate(ids):
                pid=f"{slot['request_id']}/RX{rx}";prediction=by_id[pid]
                packet=adapter.adapt(prediction,slot['raw_authority']);values=bg[:,index].astype(np.complex64)
                result=timing.score_target(values,window.sample_rate_hz,window.target['edge'],packet,
                    selection_writer(pid.replace('/','_')))
                archived=targets[pid] or {};positive=oracle(values,window.sample_rate_hz,window.target['edge'],packet,archived)
                row['cells'].append(dict(prediction_id=pid,receiver_id=rx,packet=packet,result=result,
                    original_fullwindow=archived,oracle=positive,original_evaluation_only=True))
            row['status']='complete'
        except Exception as exc:row.update(status='failed',error=repr(exc))
        rows.append(row);print(slot['request_id'],row['status'],flush=True)
        write(HERE/'checkpoints'/f'{slot["request_id"]}.json.gz',dict(row,
            elapsed_seconds=time.monotonic()-began,checkpoint_is_complete_window_outcome=True))
    write(HERE/'outcomes'/f'{case}.json.gz',dict(rows=rows,seconds=time.monotonic()-began,
        protocol_sha256=sha(HERE/'protocol.json'),expected_windows=24,expected_receiver_cells=48))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','signal','boundary','null','wrong','recorded'])
    parser.add_argument('--case');args=parser.parse_args()
    if args.action=='prepare':prepare()
    elif args.action in ['signal','boundary']:controls(args.action)
    elif args.action in ['null','wrong']:nulls(args.action=='wrong')
    else:recorded(args.case)
