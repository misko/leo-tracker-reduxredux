"""Causal catalogue/position/rate diagnostics for every inventoried large curve.

All outputs are discovery diagnostics. Per-track position searches freeze the
incumbent receiver correction and cannot establish a joint position minimum.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from functools import partial
from pathlib import Path
import sys
import time

import numpy as np
from scipy.optimize import minimize_scalar
from debug_fast_graph_unassociated import read,write
from benchmark_graph_covariance import load_case
from validate_fast_target_guard import target_guard
from stress_joint_attachment import supervise
from leo.analysis.research.track_recovery_diagnostics import shortlist,profile_rate
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from prototype_dsx01_continuous_position import latlon

ARMS=('c0','fitted_c');PHASES=np.arange(-15.,15.1,3.)
MODELS={'constant':(0.,1000.),'small_rate':(.5,1000.),'shape_only':(0.,1e9)}


def context(inventory):
    job=inventory['job'];d=load_case(Path(job['root']),job['case']);kind=job['policy_kind']
    if kind=='baseline':return d
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_history_calibrated_phase import make_problem
    from probe_ds23_frequency_events import cached
    path=Path(job['prior_guard_path']) if kind=='attachment' else Path(job['policy_path'])
    source=read(path/'result.json');p,_=d['problems']['c0'];keep=d['keep'].copy();sigma=300.;target=None
    support=read(path/'support.json');policy='nominal'
    if support['status']=='accepted':
        k=next(k for k,r in enumerate(p.rows) if r['component']==support['component']);keep[p.slices[k]]=True;policy='active'
    u=read(path/'unconstrained.json') if source['status']=='accepted' else None
    if target_guard(source,u):
        target=source['proposal']['row'];sigma=source['selected_sigma_hz'];keep[p.slices[target]]=True
    def factory(*a,**kw):
        q=make_problem(*a,**kw,support_policy=policy)
        if target is not None:q.constants[:,target]*=sigma/300.
        return q
    problems={}
    for arm,r in inventory['policy'].items():
        q=make_event_problem(d['scan'],d['node'],keep,arm,np.asarray(r['phase_reference']),d['powers'],d['means'],d['model'],[],base_problem_factory=factory)
        attach_event_predictive(q,d['entries'],d['powers']);cached(q);x=np.asarray(r['endpoint_east_north_km'])
        # Attachment adds a predictive likelihood, never calibration equations.
        expected=r.get('curved_negative_twice_elbo');actual=q.calculate(x).get('curved_negative_twice_elbo',q.calculate(x)['negative_twice_elbo'])
        if expected is not None and abs(actual-expected)>1e-4:raise ValueError(f'curved calibration replay mismatch {arm}: {actual-expected}')
        problems[arm]=(q,x)
    return dict(d,keep=keep,problems=problems,support_policy=policy,problem_factory=factory)


def exact(scan,track,y,guess,position,model):
    j=guess['candidate_index'];t=np.asarray(track['times']);rate,bias=MODELS[model]
    bank={k:scan.sky[k][[j]] for k in ('position_km','velocity_km_s')};bank['time_s']=scan.sky['time_s']
    def evaluate(phase):
        f,e=paired_phase_frequency(bank,t,np.zeros(len(t),int),np.array([phase]),*latlon(position))
        return profile_rate(y,track['rf_hz']/11.5e9*f,t,rate_sigma_hz_s=rate,bias_sigma_hz=bias),f,e
    lower=max(-15.,guess['phase_s']-3);upper=min(15.,guess['phase_s']+3)
    fit=minimize_scalar(lambda phi:float(evaluate(phi)[0]['cost'][0]),bounds=(lower,upper),method='bounded',options={'xatol':.02,'maxiter':40})
    terms,f,e=evaluate(fit.x);residual=terms['residual_hz'][0];noise=batch_noise_screen(residual[None,:],t)
    noise={k:bool(v[0]) if v.dtype==bool else float(v[0]) for k,v in noise.items()}
    shape=bool(e.min()>=0 and terms['rms_hz'][0]<=450 and noise['noise_screen_pass'])
    bounds=bool(abs(terms['bias_hz'][0])<=3000 and abs(terms['rate_hz_s'][0])<=2)
    return dict(candidate_index=j,norad=int(scan.norads[j]),phase_s=float(fit.x),position_east_north_km=position,
        model=model,cost=float(terms['cost'][0]),rms_hz=float(terms['rms_hz'][0]),
        offset_hz=float(terms['bias_hz'][0]),rate_hz_s=float(terms['rate_hz_s'][0]),alias=int(terms['alias'][0]),
        minimum_elevation_deg=float(e.min()),shape_pass=shape,physical_screen_pass=shape and bounds,
        noise=noise,times_s=t,residual_hz=residual,corrected_observation_hz=y,
        orbit_prediction_hz=track['rf_hz']/11.5e9*f,discovery_only=True)


def one(args):
    began=time.monotonic();inv=read(args.inventory);out=args.output;out.mkdir(parents=True,exist_ok=False)
    d=context(inv);scan=d['scan'];rows={r['track_id']:r for r in inv['tracks'] if r['current_large']}
    if not rows:write(out/'result.json',dict(status='no_large_tracks',tracks=[]));return
    targets=list(rows.values());observed={};initial={};positions={}
    for arm,(p,x) in d['problems'].items():
        state=p.state(x);positions['current_'+arm]=x;initial[arm]=x
        for row in targets:
            t=scan.tracks[row['track_index']];i=row['track_index']
            observed[arm,row['track_id']]=t['values']-scan.hardware(t,state['beta'])-t['rf_hz']/11.5e9*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
    for e in (-10.,0.,10.):
        for n in (-10.,0.,10.):positions[f'regional_{e:g}_{n:g}']=np.array([e,n])
    tmin=min(min(scan.tracks[r['track_index']]['times']) for r in targets)
    tmax=max(max(scan.tracks[r['track_index']]['times']) for r in targets)
    knots=np.linspace(tmin,tmax,max(2,int(np.ceil((tmax-tmin)/2))+1))
    offers={};coarse=[]
    for name,position in positions.items():
        ff=[];ee=[]
        for phase in PHASES:
            f,e=phase_frequency_grid(scan.sky,knots,*latlon(position),phase_seconds=phase)
            ff.append(f.astype(np.float32));ee.append(e.astype(np.float32))
        ff=np.array(ff);ee=np.array(ee)
        for row in targets:
            track=scan.tracks[row['track_index']];pick=np.unique(np.linspace(0,len(track['times'])-1,min(16,len(track['times']))).astype(int))
            for arm in ARMS:
                for model,(rate,bias) in MODELS.items():
                    result=shortlist(observed[arm,row['track_id']][pick],track['times'][pick],track['rf_hz']/11.5e9,
                        ff,ee,knots,PHASES,top=5,rate_sigma_hz_s=rate,bias_sigma_hz=bias)
                    offers[arm,row['track_id'],model,name]=result
                    coarse.append(dict(track_id=row['track_id'],arm=arm,model=model,position=name,candidates=result))
        print(inv['job']['label'],'grid',name,flush=True)
    write(out/'coarse.json',coarse)
    results=[]
    for row in targets:
        track=scan.tracks[row['track_index']];trials={}
        for arm in ARMS:trials[arm]={}
        for model in MODELS:
            # Union nominations before exact fitting: both c arms receive the
            # same identities, regional starts, phase windows and budget.
            local=[];regional=[]
            for arm in ARMS:
                local+=offers[arm,row['track_id'],model,'current_'+arm][:3]
                all_offers=[dict(g,position_name=name) for name in positions for g in offers[arm,row['track_id'],model,name]]
                all_offers.sort(key=lambda r:r['cost']);seen=set()
                for g in all_offers:
                    if g['candidate_index'] in seen:continue
                    seen.add(g['candidate_index']);regional.append(g)
                    if len(seen)>=3:break
            local=list({(g['candidate_index'],g['phase_s']):g for g in local}.values())
            regional=list({(g['candidate_index'],g['phase_s'],g['position_name']):g for g in regional}.values())
            for arm in ARMS:
                checked=[dict(exact(scan,track,observed[arm,row['track_id']],g,initial[arm],model),search='current') for g in local]
                checked += [dict(exact(scan,track,observed[arm,row['track_id']],g,positions[g['position_name']],model),search='regional') for g in regional]
                trials[arm][model]=checked
        p,_=d['problems']['c0'];nominee=next((r['candidate_norad'] for r in p.rows if r['component']==track['key']),None)
        record=dict(track_id=row['track_id'],component=track['key'],track_index=row['track_index'],
             remaining_points=len(row['observation_ids']),full_points=len(track['times']),original_nominee=nominee,
             engine_curved=row['track_index'] in scan.curved,engine_member=row['track_index'] in p.members,
             pieces=len(track['pieces']),trials=trials)
        results.append(record);write(out/(row['track_id']+'.json'),record)
        print(inv['job']['label'],track['key'],'done',flush=True)
    write(out/'result.json',dict(status='complete',job=inv['job'],tracks=results,seconds=time.monotonic()-began,
        calibration='incumbent receiver corrections held fixed while searching each track',
        no_joint_localization_claim=True,no_new_associations=True))


def run(args):
    protocol=read(args.inventory/'protocol.json');args.output.mkdir(parents=True,exist_ok=False)
    jobs=[j for j in protocol['jobs'] if (args.inventory/j['job_id']/'inventory.json').exists()]
    jobs.sort(key=lambda j:('DS24' not in j['scopes'] and 'session research' not in j['scopes'],j['label']))
    write(args.output/'protocol.json',dict(jobs=jobs,workers=8,case_seconds=480,phase_grid=PHASES,
         region_grid_km=[-10,0,10],models=MODELS,regional_receiver_calibration_frozen=True,
         coarse_interpolation_only=True,exact_full_point_refinement=True,top_distinct_candidates=3,
         GPS_used=False,future_TLE=False,acceptance_policy_changed=False))
    def work(job):
        cmd=[sys.executable,__file__,'one','--inventory',str(args.inventory/job['job_id']/'inventory.json'),
             '--output',str(args.output/job['job_id'])]
        r=dict(job_id=job['job_id'],label=job['label'],**supervise(cmd,args.output/(job['job_id']+'.log'),480))
        write(args.output/(job['job_id']+'-terminal.json'),r);return r
    rows=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):
            r=f.result();rows.append(r);print(r,flush=True)
    write(args.output/'execution.json',rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('one','run'))
    p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();one(a) if a.mode=='one' else run(a)
