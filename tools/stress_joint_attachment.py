"""Known-origin target controls through the complete graph recovery procedure.

These are conditional injection tests: the incumbent graph and its calibration
data are real and fixed. They do not simulate acquisition or graph construction.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import numpy as np
from debug_fast_graph_unassociated import read, write
from test_joint_high_channel_recovery import context, nominate, case
from probe_high_channel_correlated_noise import entries_for_targets, prediction_geometry
from leo.analysis.research.retained_track_likelihood import PERIOD

KINDS=('correct','split_identity','joined_identity','step150','step300','curvature250')
SEEDS=(4081,4082,4083)


def inject(mean, alternate, times, owners, kind, seed):
    """Generate paired lanes with shared time noise and explicit source labels."""
    mean=np.asarray(mean,float); alternate=np.asarray(alternate,float)
    times=np.asarray(times,float); owners=np.asarray(owners)
    if kind not in KINDS or len(set(owners))!=2:
        raise ValueError('known control and exactly two lanes required')
    labels=np.full(len(times),57701); signal=mean.copy()
    if kind=='split_identity':
        mask=owners==1; signal[mask]=alternate[mask]; labels[mask]=58101
    elif kind=='joined_identity':
        for owner in np.unique(owners):
            lane=owners==owner; seam=np.median(times[lane]); mask=lane & (times>=seam)
            pivot=np.flatnonzero(lane)[np.argmin(abs(times[lane]-seam))]
            # A continuous bad join is harder than a large arbitrary jump.
            signal[mask]=alternate[mask]+mean[pivot]-alternate[pivot]; labels[mask]=58101
    elif kind.startswith('step'):
        signal += (times>=np.median(times))*float(kind[4:])
    elif kind=='curvature250':
        x=(times-times.min())/np.ptp(times)*2-1
        signal += 250*(x*x-np.mean(x*x))
    covariance=80.**2*np.eye(len(times))+80.**2*np.exp(-abs(times[:,None]-times[None,:])/2.)
    rng=np.random.default_rng(seed)
    noise=np.linalg.cholesky(covariance)@rng.normal(size=len(times))
    return signal+noise,dict(kind=kind,seed=seed,labels=labels,mean_hz=signal,
                            noise_hz=noise,times_s=times,owners=owners,
                            white_sd_hz=80,shared_sd_hz=80,timescale_s=2)


def one(args):
    d,baseline=context(args.root,'SCAN',args.source); targets=nominate(d,baseline)
    if len(targets)!=2:raise ValueError('pilot requires its two nominated lanes')
    p,x=d['problems']['c0']; model=dict(white_hz=80.,amplitude_hz=80.,timescale_s=2.)
    means={};aliases={}
    for satellite in (57701,58101):
        extras=entries_for_targets(d,targets,satellite)
        fn,view,_,_,_=prediction_geometry(p,[],d['powers'],extras,model)
        _,raw,_,_=fn(x)
        values=np.concatenate([d['scan'].tracks[e['track_index']]['values']+e['alias']*PERIOD for e in extras])
        # Put both orbits in the same original graph alias coordinates.
        means[satellite]=values-raw-np.repeat([e['alias']*PERIOD for e in extras],[e['points'] for e in extras])
        aliases[satellite]=[e['alias'] for e in extras]
    owners=np.repeat(np.arange(len(targets)),[len(d['scan'].tracks[p.members[k]]['times']) for k in targets])
    values,truth=inject(means[57701],means[58101],view.flat_times,owners,args.kind,args.seed)
    for lane,k in enumerate(targets):
        if p.keep[p.slices[k]].any():raise ValueError('cannot mutate an incumbent calibration target')
        d['scan'].tracks[p.members[k]]['values']=values[owners==lane].copy()
    # Candidate search, independent covariance estimation, randomized prediction,
    # both position fits, old-point preservation and all final gates rerun.
    case(SimpleNamespace(output=args.output,case='SCAN'), supplied_context=(d,baseline))
    write(args.output/'injected_truth.json',dict(truth,aliases=aliases,
          generating_position_east_north_km=x,position_source='RF incumbent c0 endpoint; no GPS',
          original_calibration_observations_unchanged=True))


def supervise(command, logfile, cap):
    mark=time.monotonic();status='complete';reason=None
    with logfile.open('x') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code=child.wait(timeout=cap)
            if code:status='failed';reason=f'exit {code}'
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            status='timeout';reason=f'{cap}s cap'
    return dict(status=status,reason=reason,seconds=time.monotonic()-mark)


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    paths=[Path(__file__),Path(__file__).with_name('test_joint_high_channel_recovery.py'),
           Path(__file__).with_name('probe_high_channel_correlated_noise.py')]
    jobs=[dict(kind=k,seed=s,name=f'{k}-{s}') for k in KINDS for s in SEEDS]
    write(args.output/'protocol.json',dict(jobs=jobs,workers=4,seconds_per_job=240,
          source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
          budgets='unchanged complete recovery, all three variants, both c arms, 5 phase rounds x 48 fit iterations',
          alpha_unchanged=True,thresholds_unchanged=True,
          false_identity_controls=['split_identity','joined_identity'],
          structure_controls=['step150','step300','curvature250'],
          scope='conditional graph-level stress test; real incumbent data, estimated covariance rerun; not an end-to-end acquisition false-association rate',
          promotion=dict(minimum_unused_applicable_recordings=20,minimum_independent_successful_recoveries=5,
                         require_no_false_identity_accepts_in_controls=True,
                         maximum_individual_error_regression_km=.25,maximum_p95_error_regression_km=.10,
                         mean_error_improvement_required_in_both_c_arms=True,
                         independent_safety_calibration_required=True,
                         no_error_reporting_without_verified_site=True)))
    def work(job):
        command=[sys.executable,__file__,'one','--root',str(args.root),'--source',str(args.source),
                 '--kind',job['kind'],'--seed',str(job['seed']),'--output',str(args.output/job['name'])]
        result=dict(job,**supervise(command,args.output/(job['name']+'.log'),240))
        write(args.output/(job['name']+'-terminal.json'),result);return result
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):
            r=f.result();results.append(r);print(r,flush=True)
    write(args.output/'execution.json',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','one'))
    for name in ('root','source','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--kind',choices=KINDS);p.add_argument('--seed',type=int)
    a=p.parse_args();run(a) if a.mode=='run' else one(a)
