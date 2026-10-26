"""Bounded disjoint temporal guiding, using unchanged public historical ports."""
import argparse
import dataclasses
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace
import numpy as np

HERE=Path(__file__).resolve().parent
PRIOR=Path('/srv/bulk/leo/research/ds24-ch78-diagnosis-r02/detection')


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


old=module('unchanged_r02_detection',PRIOR/'study.py')
HALF=100000
SCENARIOS={'zero_zero':(None,None),'weak_weak':(-24,-24),'strong_weak':(-18,-24),'strong_zero':(-18,None)}


def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def encode(v):
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    raise TypeError(type(v).__name__)
def write(p,v):
    with Path(p).open('x')as f:json.dump(v,f,indent=2,default=encode,allow_nan=False);f.write('\n')


def bound():
    for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(k)!='1':raise ValueError('BLAS1 required')
    def timeout(*_):raise TimeoutError('580-second worker bound')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(580)
    p=load(HERE/'protocol.json')
    for path,h in p['files'].items():
        if sha(path)!=h:raise ValueError('frozen file changed: '+path)
    if old.replay.runtime_identity()!=p['identity']:raise ValueError('historical identity changed')
    return p


def pack(window,values,offset):
    """Restrict support without copying, padding or changing source time units."""
    values=np.asarray(values,dtype=np.complex64)
    a=dict(window.acquisition)
    a['sample_start']=window.acquisition['sample_start']+offset
    a['sample_end']=a['sample_start']+len(values)
    w=dataclasses.replace(window,acquisition=a,samples=np.stack((values.real,values.imag),axis=-1))
    receipt=dict(start_counter=a['sample_start'],stop_counter=a['sample_end'],offset_samples=offset,
        native_samples=len(values),generation=a['generation'],source_IQ_sha256=window.iq_sha256,
        synthetic_overlay=True,support_sha256=hashlib.sha256(values.astype('<c8').tobytes()).hexdigest())
    return w,receipt


def blind(window,ids):
    from leo.scanner.fast_scan_analysis import production_glrt
    return [r.model_dump(mode='json')for r in production_glrt(window,ids)]


def explicit_ten_ms(window,ids):
    from leo.scanner.fast_scan_detector import Glrt64SearchGeometry,analyze_glrt64_dwell
    from leo.analysis.starlink.acquisition import ReceiverFrequencyCalibration
    from leo.analysis.starlink.templates import edge_frequencies_hz
    from leo.contracts.digests import canonical_digest
    target=window.target;actual=window.acquisition['actual_if_center_hz']
    center=target['rf_center_hz']-target['lnb_lo_hz']-actual
    offsets=edge_frequencies_hz(target['edge']);halfband=window.sample_rate_hz/2
    width=min(800000.,center+float(offsets.min())+halfband,halfband-center-float(offsets.max()))
    geometry=Glrt64SearchGeometry(tuple(ReceiverFrequencyCalibration(str(rx),center,
        canonical_digest({'target':target,'actual_if':actual,'rx':rx}).removeprefix('sha256:'))for rx in ids),
        -width,width,tuple(range(2,302,14)))
    conf=SimpleNamespace(dwell_samples=HALF,probe_samples=HALF,probe_stride_ms=10,probe_stride_samples=HALF,
        scheduled_probe_count=1,sample_rate_hz=window.sample_rate_hz,receiver_ids=ids,probe_ms=10,
        glrt64_margin_gate=.025,maximum_acquisition_candidates=8)
    values=window.samples[:,:,0]+1j*window.samples[:,:,1]
    result=analyze_glrt64_dwell(values,conf,edge=target['edge'],search_geometry=geometry)
    return [dict(receiver_id=p.receiver_id,candidates=[dataclasses.asdict(c)for c in p.candidates])for p in result.probes]


def normalize_public(rows):
    """Public dataclass and public contract use different integer-epoch names."""
    out=[]
    for rx in rows:
        candidates=[]
        for c in rx['candidates']:
            value=dict(c)
            if 'epoch_sample'in value:value['integer_epoch_sample']=value.pop('epoch_sample')
            candidates.append(value)
        out.append(dict(receiver_id=rx['receiver_id'],candidates=candidates))
    return out


def donors(earlier):
    """Only measured earlier fields enter this estimator; no injected truth."""
    return sorted([c for c in earlier['candidates']if c['fractional_epoch_status']=='complete'
        and c['fractional_margin']is not None and c['fractional_margin']>=.025],key=lambda c:c['candidate_rank'])


def guide(later,rate,edge,earlier,delta_samples):
    """Prespecified all-proposal diagnostic; primary is always first original rank."""
    from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
    selected=donors(earlier)
    if len(selected)>8:raise ValueError('donor cap exceeded')
    results=[]
    for c in selected:
        epoch=(c['integer_epoch_sample']+c['fractional_epoch_offset_samples']-delta_samples)%(rate/750.)
        integer=math.floor(epoch)
        score=conditioned_glrt64_score(later,rate,epoch_sample=integer,
            fractional_epoch_offset_samples=epoch-integer,acquired_cfo_hz=c['fractional_tracking_cfo_hz'],edge=edge)
        results.append(dict(donor_rank=c['candidate_rank'],propagated_epoch_samples=epoch,
            donor_tracking_CFO_hz=c['fractional_tracking_cfo_hz'],score=dataclasses.asdict(score),passed=bool(score.margin>=.025)))
    return dict(proposals=results,primary=results[0]if results else None,
        primary_accepted=bool(results and results[0]['passed']),any_accepted=any(r['passed']for r in results),
        active_donors=len(results),truth_used=False)


def identity(epoch,cfo,rate,offset):
    expected=(old.EPOCH-offset)%(rate/750.)
    error=(epoch-expected+rate/1500)%(rate/750.)-rate/1500
    return dict(timing_error_samples=float(error),CFO_error_hz=float(cfo-old.CFO),
        matched=bool(abs(error)<=2 and abs(cfo-old.CFO)<=100))


def evaluate(late_values,rate,edge,earlier,later,offset=HALF,injected=True):
    """Truth is accessed only here, after both blind and guided estimates exist."""
    guided=guide(late_values,rate,edge,earlier,offset)
    for r in guided['proposals']:
        r['truth']=identity(r['propagated_epoch_samples'],r['score']['tracking_cfo_hz'],rate,offset)
    primary=guided['primary']
    guided['primary_recovered']=bool(injected and primary and primary['passed']and primary['truth']['matched'])
    guided['any_recovered']=bool(injected and any(r['passed']and r['truth']['matched']for r in guided['proposals']))
    donor_evaluation=[dict(rank=c['candidate_rank'],**identity(c['integer_epoch_sample']+
        c['fractional_epoch_offset_samples'],c['fractional_tracking_cfo_hz'],rate,0))for c in donors(earlier)]
    eligible=[]
    for c in later['candidates']:
        if c['fractional_epoch_status']=='complete'and c['fractional_margin']is not None:
            eligible.append(dict(rank=c['candidate_rank'],passed=bool(c['fractional_margin']>=.025),
                **identity(c['integer_epoch_sample']+c['fractional_epoch_offset_samples'],c['fractional_tracking_cfo_hz'],rate,offset)))
    from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
    epoch=(old.EPOCH-offset)%(rate/750.)
    oracle=conditioned_glrt64_score(late_values,rate,epoch_sample=math.floor(epoch),
        fractional_epoch_offset_samples=epoch-math.floor(epoch),acquired_cfo_hz=old.CFO,edge=edge)
    return dict(guided=guided,donor_truth_evaluation=donor_evaluation,blind_truth_evaluation=eligible,
        blind_recovered=bool(injected and any(c['passed']and c['matched']for c in eligible)),
        blind_any_accepted=any(c['passed']for c in eligible),oracle=dataclasses.asdict(oracle),
        oracle_accepted=bool(oracle.margin>=.025),late_injected=injected)


def superpose(background,wave,db):
    return background.copy()if db is None else old.injection(background,wave,db)[0]


def prepare():
    prior_protocol=load(PRIOR/'protocol.json')
    panel=load(PRIOR/'panel.json')
    for p,h in prior_protocol['files'].items():
        if sha(p)!=h:raise ValueError('round2 frozen dependency changed: '+p)
    write(HERE/'panel.json',panel)
    files={str(HERE/name):sha(HERE/name)for name in ['PROTOCOL.md','study.py','test_study.py','panel.json']}
    files.update(prior_protocol['files'])
    for p in [PRIOR/'verification.json',old.PRIOR/'recorded/replay.py',old.PRIOR/'influence/raw_metadata.py']:
        files[str(p)]=sha(p)
    write(HERE/'protocol.json',dict(schema='ch78-disjoint-donor-confirmation/v1',frozen_utc_ns=time.time_ns(),
        files=files,identity=old.replay.runtime_identity(),scenarios=SCENARIOS,
        source_split_samples=HALF,requested_slots=8,requested_RX_cells=16,truth_tolerances=[2,100],
        active_null_paired_trials_per_edge=64,independent_noise_only_paired_trials=32,
        seed_active=3026102601,seed_noise=3026102602,process_bound_seconds=580,
        IQ_reads_before_freeze=0,maximum_guided_donors=8,no_GPS=True,no_new_RF=True))
    print('frozen',sha(HERE/'protocol.json'),flush=True)


def preflight():
    began=time.monotonic();bound();slot=load(HERE/'panel.json')['slots'][0]
    window,ids,background,receipt=old.opened(slot);rows=[]
    for start in [0,HALF]:
        half,support=pack(window,background[start:start+HALF],start)
        a=normalize_public(blind(half,ids));b=normalize_public(explicit_ten_ms(half,ids))
        if a!=b:raise ValueError('public split10ms full candidate parity failed')
        rows.append(dict(support=support,public10ms_vs_unchanged_production_all_candidates_equal=True,blind=a))
    wave=old.analytic(2*HALF,window.sample_rate_hz,window.target['edge'])
    z=np.column_stack([superpose(background[:,i],wave,-18)for i in range(len(ids))])
    early,_=pack(window,z[:HALF],0)
    late_values=np.column_stack([superpose(background[HALF:,i],wave[HALF:],-24)for i in range(len(ids))]).astype(np.complex64)
    late,_=pack(window,late_values,HALF)
    d=normalize_public(blind(early,ids));l=normalize_public(blind(late,ids))
    probe=[evaluate(late_values[:,i],window.sample_rate_hz,window.target['edge'],d[i],l[i])for i in range(len(ids))]
    write(HERE/'preflight.json',dict(protocol_sha256=sha(HERE/'protocol.json'),slot=slot['request_id'],
        original20ms_parity=receipt,split_parity=rows,mechanism_probe=probe,seconds=time.monotonic()-began,
        supported=True,no_replacement=True))
    print('preflight',time.monotonic()-began,flush=True)


def recorded():
    began=time.monotonic();bound();pre=load(HERE/'preflight.json')
    if not pre['supported']:raise ValueError('preflight not supported')
    results=[]
    for slot in load(HERE/'panel.json')['slots']:
        item=dict(request_id=slot['request_id'],status='in_progress',scenarios={})
        try:
            window,ids,bg,receipt=old.opened(slot);rate=window.sample_rate_hz;edge=window.target['edge']
            wave=old.analytic(len(bg),rate,edge);item['receipt']=receipt
            for label,(early_db,late_db)in SCENARIOS.items():
                early_values=np.column_stack([superpose(bg[:HALF,i],wave[:HALF],early_db)for i in range(len(ids))]).astype(np.complex64)
                late_values=np.column_stack([superpose(bg[HALF:,i],wave[HALF:],late_db)for i in range(len(ids))]).astype(np.complex64)
                ew,es=pack(window,early_values,0);lw,ls=pack(window,late_values,HALF)
                if es['stop_counter']!=ls['start_counter']:raise ValueError('native split ownership overlaps/gaps')
                earlier=normalize_public(blind(ew,ids));later=normalize_public(blind(lw,ids))
                outcomes=[dict(receiver=rx+1,channel=slot['channel'],edge=edge,
                    **evaluate(late_values[:,i],rate,edge,earlier[i],later[i],injected=late_db is not None))for i,rx in enumerate(ids)]
                item['scenarios'][label]=dict(earlier_support=es,later_support=ls,earlier_blind=earlier,
                    later_blind=later,outcomes=outcomes,early_db=early_db,late_db=late_db,
                    waveform_phase_continuous=True,amplitude_step_only=True)
            item['status']='complete'
        except Exception as exc:item.update(status='failed',error=repr(exc))
        results.append(item);print(slot['request_id'],item['status'],flush=True)
    write(HERE/'recorded.json',dict(rows=results,seconds=time.monotonic()-began,
        protocol_sha256=sha(HERE/'protocol.json'),runtime_identity_unchanged=old.replay.runtime_identity()==load(HERE/'protocol.json')['identity']))


def nulls(mode):
    began=time.monotonic();protocol=bound();rows=[];banks=[]
    seed=protocol['seed_active']if mode=='active'else protocol['seed_noise']
    rng=np.random.default_rng(seed)
    panel=load(HERE/'panel.json')['slots']
    # Only public geometry/authority is needed; zero arrays have no source IQ ownership.
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow
    for edge in ['lower','upper']:
        slot=next(s for s in panel if s['raw_authority']['target']['edge']==edge)
        a=slot['raw_authority']['index']['acquisition'];target=slot['raw_authority']['target']
        template=VerifiedFastWindow(0,'synthetic-no-recording-IQ',a,target,np.zeros((2*HALF,2,2)),10_000_000)
        donor=None
        if mode=='active':
            noise=(rng.normal(size=(HALF,2))+1j*rng.normal(size=(HALF,2)))/np.sqrt(2)
            wave=old.analytic(2*HALF,10_000_000,edge)[:HALF]
            values=np.column_stack([superpose(noise[:,i],wave,-18)for i in range(2)]).astype(np.complex64)
            w,_=pack(template,values,0);donor=normalize_public(blind(w,(0,1)))
            banks.append(dict(edge=edge,donors=donor))
        count=protocol['active_null_paired_trials_per_edge']if mode=='active'else protocol['independent_noise_only_paired_trials']//2
        for trial in range(count):
            later=(rng.normal(size=(HALF,2))+1j*rng.normal(size=(HALF,2)))/np.sqrt(2)
            later=later.astype(np.complex64)
            if mode=='noise':
                early=(rng.normal(size=(HALF,2))+1j*rng.normal(size=(HALF,2)))/np.sqrt(2)
                ew,_=pack(template,early,0);donor=normalize_public(blind(ew,(0,1)))
            lw,_=pack(template,later,HALF);later_blind=normalize_public(blind(lw,(0,1)))
            for i in range(2):
                guided=guide(later[:,i],10_000_000,edge,donor[i],HALF)
                accepted=[c for c in later_blind[i]['candidates']if c['fractional_epoch_status']=='complete'
                    and c['fractional_margin']is not None and c['fractional_margin']>=.025]
                rows.append(dict(edge=edge,receiver=i+1,trial=trial,guided=guided,
                    blind_any_accepted=bool(accepted),blind_candidates=later_blind[i]['candidates'],
                    null_later_sha256=hashlib.sha256(later[:,i].astype('<c8').tobytes()).hexdigest()))
            if trial%16==0:print(mode,edge,trial,flush=True)
    write(HERE/(mode+'_null.json'),dict(rows=rows,donor_banks=banks,seed=seed,seconds=time.monotonic()-began,
        conditional_active_donor=mode=='active',independent_later_draws=len(rows),
        protocol_sha256=sha(HERE/'protocol.json')))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','preflight','recorded','active_null','noise_null']);a=p.parse_args().action
    if a=='prepare':prepare()
    elif a=='preflight':preflight()
    elif a=='recorded':recorded()
    else:nulls(a.split('_')[0])
