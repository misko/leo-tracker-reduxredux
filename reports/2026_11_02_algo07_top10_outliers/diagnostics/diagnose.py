"""Bounded offline composed-ALGO06 outlier diagnostics; never alter owners."""
import argparse, csv, hashlib, json, signal, time
from pathlib import Path
import numpy as np
from algo07_science import engine as e
from algo07_science.diagnose import derivatives, refit, objective
from algo06_science.common import read, write
from algo06_science.position import family_score
from prototype_dsx01_continuous_position import latlon, CENTER
from phase_reference_checks import phase_refresh
from probe_algo03_feasible_recovery import gate_slacks
from audit_explicit_phase_endpoint import exact_gate_replay
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from debug_fast_graph_unassociated import memberships
from inactive_graph_fragment import original_graph_view

ROOT=Path(__file__).resolve().parent
INPUT=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds26_ds27_causal_variants')
CASES=['DS26-0203','DS26-0070','DS26-0072','DS26-0221','DS26-0044','DS26-0100','DS26-0014','DS26-0201','DS26-0309','DS26-0209']
ARMS=('c0','fitted_c')
SITE=(37.849061591561885,-122.48574968092912)
SITE_X=np.array([(SITE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),(SITE[0]-CENTER[0])*111])

def error(x):
    a,b=np.deg2rad(latlon(x)),np.deg2rad(SITE)
    h=np.sin((a[0]-b[0])/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin((a[1]-b[1])/2)**2
    return float(6371008.8*2*np.arcsin(np.sqrt(h)))

def load(case):
    e.configure(INPUT,ROOT);e.ROOTS['DS26']=INPUT
    return e.load_case(case)

def frozen_published_owners(case,z):
    """Compose only the explicitly accepted ALGO06 family, never extensions."""
    owners={arm:dict(z['baseline_owners'][arm]) for arm in ARMS}
    result=read(INPUT/'position'/case/'result.json');decision=result['decisions']['72h_30s']
    if decision['status']=='qualified':
        ent=result['trials'][decision['trial']]['entry']
        for arm in ARMS:
            for oid in ent['observation_ids']:
                if oid in owners[arm]:raise ValueError('duplicate accepted ALGO06 owner')
                owners[arm][oid]=ent['norad']
    return owners

def stats(t,r):
    t=np.asarray(t);r=np.asarray(r);u=t-t.mean()
    return dict(n=len(r),span_s=float(np.ptp(t)),mean_hz=float(r.mean()),rms_hz=float(np.sqrt(np.mean(r*r))),
        slope_hz_s=float(u@r/(u@u)) if u@u else 0.,
        lag1=float(np.corrcoef(r[:-1],r[1:])[0,1]) if len(r)>3 and np.std(r)>0 and np.std(r[:-1])>0 and np.std(r[1:])>0 else None,
        noise={k:v[0].item() for k,v in batch_noise_screen(r[None,:],t).items()})

def gates(p,d,x,z,arm):
    slack=gate_slacks(p,x,d['entries']);exact=[]
    for j in sorted({r['candidate_index'] for r,s in zip(p.rows,p.slices) if p.keep[s].any()}):
        p.explicit_phase_family=j;v=exact_gate_replay(p,x,d['entries'])
        exact.append(dict(norad=int(p.scan.norads[j]),all_pass=v['all_pass'],minimum_slack=v['minimum_slack'],
            failed={k:v for k,v in v['all_gate_slacks'].items() if v<0},maximum_linearization_difference_hz=v['maximum_linearization_difference_hz']))
    if hasattr(p,'explicit_phase_family'):del p.explicit_phase_family
    _,fd=family_score(d['families'],d,p,x,details=True)
    mixture_pass=all(g['compatible'] for f in fd for g in f['gates'])
    _,_,_,owners=memberships(original_graph_view(p,len(p.scan.index)),x,d['entries'])
    for f in d['families']:
        for ent in f.entries:owners.update({o:ent['norad'] for o in ent['observation_ids']})
    old=z['baseline_owners'][arm]
    return dict(all_base_gates_pass=min(slack.values())>=0,minimum_gate_slack=min(slack.values()),
        failed_gates={k:v for k,v in slack.items() if v<0},gate_slacks=slack,exact_orbit_checks=exact,
        mixture_gates_pass=mixture_pass,mixture_details=fd,
        all_gates_pass=min(slack.values())>=0 and all(v['all_pass'] for v in exact) and mixture_pass,
        proposed_owners=owners,lost_ids=[o for o in old if o not in owners],added_ids=[o for o in owners if o not in old],
        reassigned_ids=[o for o,n in old.items() if o in owners and owners[o]!=n])

def inventory(d,z):
    obs=read(Path(z['native_path'])/'observations.json');ids={o['observation_id'] for o in obs}
    if len(ids)!=len(obs):raise ValueError('native export has duplicate observation IDs')
    native_tracks=read(Path(z['native_path'])/'tracks.json')
    graph={o for tr in native_tracks for o in tr['observation_ids']};arms={}
    for a in ARMS:
        owners=z['baseline_owners'][a]
        if not set(owners)<=ids:raise ValueError('owner outside native export')
        arms[a]=dict(associated=len(owners),native=len(ids),percent=100*len(owners)/len(ids),
            graph_unassociated=len((graph&ids)-set(owners)),untracked=len(ids-graph-set(owners)))
    # Canonical graph source inventory; native IDs deduplicate overlapping views.
    segments=[];seen=set();owners=z['baseline_owners']['fitted_c']
    for tr in native_tracks:
        selected=[(float(t),o) for t,o in zip(tr['times'],tr['observation_ids']) if o in ids and o not in owners]
        selected.sort();groups=[]
        for t,o in selected:
            if not groups or t-groups[-1][-1][0]>5:groups.append([])
            groups[-1].append((t,o))
        for group in groups:
            key=tuple(sorted({o for t,o in group}))
            if not key or key in seen:continue
            seen.add(key);segments.append(dict(component=tr['key'],receiver=tr['receiver'],channel=tr['channel'],
                n=len(key),span_s=group[-1][0]-group[0][0],start_s=group[0][0],end_s=group[-1][0],observation_ids=key))
    segments.sort(key=lambda r:(-r['span_s'],-r['n'],r['component']))
    return dict(arms=arms,unique_native_count=len(ids),native_sha256=hashlib.sha256((Path(z['native_path'])/'observations.json').read_bytes()).hexdigest(),
        longest_unassociated=segments[:10],ranking='native graph sources by duration, gaps >5 s; overlapping identical ID sets deduplicated; not a sky-candidate search')

def audit(case,d,z,replay):
    out=ROOT/case;out.mkdir(parents=True,exist_ok=True);rows=[];arms={}
    write(out/'inventory.json',inventory(d,z));write(out/'replay.json',replay);write(out/'published_owners.json',z['baseline_owners'])
    for a,(p,x) in d['problems'].items():
        c=p.calculate(x);s=p.state(x);fun=lambda v:objective(p,d,v);g,H=derivatives(fun,x)
        _,closure=phase_refresh(s['phases'][p.labels],p.reference,limit_s=30)
        active=sorted({r['candidate_norad'] for r,sl in zip(p.rows,p.slices) if p.keep[sl].any()}|{ent['norad'] for ent in d['entries']}|{ent['norad'] for f in d['families'] for ent in f.entries})
        influence=[]
        for n in active:
            q,dd=e.build(d,z,a,p.reference,omit=n)
            gf=np.array([(objective(q,dd,x+v)-objective(q,dd,x-v))/.1 for v in np.eye(2)*.05])
            shift=-np.linalg.pinv(H)@(gf-g)
            influence.append(dict(norad=n,gradient_difference=gf-g,local_predicted_shift_km=shift,shift_norm_km=float(np.linalg.norm(shift)),
                curved_points=sum(int(p.keep[sl].sum()) for r,sl in zip(p.rows,p.slices) if r['candidate_norad']==n),
                associated_points=sum(v==n for v in z['baseline_owners'][a].values())))
        for row,i,sl in zip(p.rows,p.members,p.slices):
            use=p.keep[sl]
            if not use.any():continue
            tr=p.scan.tracks[i];rr=c['conditional_residual_hz'][sl][use];tt=tr['times'][use]
            rows.append(dict(arm=a,kind='curved_conditional',component=row['component'],norad=row['candidate_norad'],receiver=tr['receiver'],channel=tr['channel'],
                pieces=len(tr['pieces']),observation_ids=[o for o,u in zip(tr['observation_ids'],use) if u],times_s=tt,residual_hz=rr,**stats(tt,rr)))
        for ent,sl in zip(d['entries'],getattr(p,'linear_slices',[])):
            tr=p.scan.tracks[ent['track_index']];rr=c['linear_raw_prediction_residual_hz'][sl]
            rows.append(dict(arm=a,kind='linear_raw_prediction',component=ent['component'],norad=ent['norad'],receiver=tr['receiver'],channel=tr['channel'],
                pieces=len(tr['pieces']),observation_ids=ent['observation_ids'],times_s=tr['times'],residual_hz=rr,**stats(tr['times'],rr)))
        validation=gates(p,d,x,z,a)
        for fi,f in enumerate(validation['mixture_details']):
            for ent,diag in zip(d['families'][fi].entries,f['diagnostics']):
                tr=p.scan.tracks[ent['track_index']];rr=np.asarray(diag['raw_residual_hz']);tt=np.asarray(diag['times_s'])
                rows.append(dict(arm=a,kind='new_family_raw_prediction',component=ent['component'],norad=ent['norad'],receiver=tr['receiver'],channel=tr['channel'],pieces=len(tr['pieces']),
                    observation_ids=ent['observation_ids'],times_s=tt,residual_hz=rr,**stats(tt,rr)))
        begin=p.hardware.shape[1]+p.smooth.shape[1];params=[]
        for k,j in enumerate(p.labels):
            orb=c['coefficient'][begin+len(p.labels)+3*p.supported.index(j):begin+len(p.labels)+3*p.supported.index(j)+3] if j in p.supported else []
            params.append(dict(norad=int(p.scan.norads[j]),phase_s=float(s['phases'][j]),phase_prior_mean_s=float(d['means'][k]),phase_sigma_s=float(p.phase_sigma[k]),
                phase_standardized=float(c['latent_coefficient'][begin+k]),phase_prior_precision=float(c['coefficient_prior_precision'][begin+k]),orbital_standardized=orb))
        gx=np.linspace(SITE_X[0]-5,SITE_X[0]+5,7);gy=np.linspace(SITE_X[1]-5,SITE_X[1]+5,7)
        arms[a]=dict(x=x,latlon=latlon(x),error_m=error(x),objective=fun(x),rms_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
            gradient=g,hessian=H,eigenvalues=np.linalg.eigvalsh(H),phase_reference_check=closure,beta=s['beta'],family_influence=influence,parameters=params,
            grid_east=gx,grid_north=gy,surface=[[fun(np.array([east,north])) for east in gx] for north in gy],
            surface_scope='oracle-position diagnostic, 10 km square centered on evaluation truth; fixed associations and phase references; no estimate selected here',
            decomposition={k:c[k] for k in ['quadratic','logvolume','gamma_cost','normalization_constant','negative_twice_elbo','precision_iterations','final_log_precision_change'] if k in c})
        write(out/('published_gates_'+a+'.json'),validation)
        np.savez_compressed(out/(a+'-native-fit.npz'),times=p.flat_times,values=p.values,keep=p.keep,residual=c['conditional_residual_hz'],orbit=p.q*c['frequency'],radio_adjusted=p.values-c['conditional_residual_hz'],coefficient=c['coefficient'],phase=s['phases'],beta=s['beta'],smooth=s['smooth'])
        print(case,a,'audit',round(error(x),1),'families',len(active),flush=True)
    write(out/'track_residuals.json',rows);write(out/'audit.json',dict(case=case,replay=replay,arms=arms,scan_receipt=z['scan_receipt'],input_sha256=hashlib.sha256((INPUT/'inputs'/(case+'.json')).read_bytes()).hexdigest()))
    rank={}
    for a in ARMS:
        for f in arms[a]['family_influence']:rank[f['norad']]=rank.get(f['norad'],0)+f['shift_norm_km']
    selected=sorted(rank,key=lambda n:(-rank[n],n))[:4]
    write(out/'fit-plan.json',dict(selected=selected,rank=rank,total_families=len(rank),coverage='top four by summed c-arm local RF omission displacement; all families audited; no GPS selection',rounds=15,maxiter=35,maxfun=140,phase_tolerance_s=.01))
    return selected

def run(case,mode):
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('1200 second per-case cap')));signal.alarm(1200)
    out=ROOT/case;out.mkdir(parents=True,exist_ok=True)
    try:
        d,z,replay=load(case)
        selected=audit(case,d,z,replay) if mode!='fits' else read(out/'fit-plan.json')['selected']
        if mode=='audit':return
        tests=[('continue',None,1.,'saved'),('regional_center',None,1.,'center'),('phase_sigma_x2',None,2.,'saved')]+[(f'omit_{n}',n,1.,'saved') for n in selected]
        for tag,n,scale,start in tests:
            if (out/(tag+'.json')).exists():continue
            pair={}
            for a in ARMS:
                path=out/(tag+'-'+a+'.json')
                if path.exists():pair[a]=read(path);continue
                row=refit(d,z,a,np.zeros(2) if start=='center' else d['problems'][a][1],n,scale,rounds=15)
                # Evaluation truth is read only after RF fitting completes.
                row['error_m']=error(np.array(row['x']));p,dd=e.build(d,z,a,np.asarray(row['reference']),n,scale)
                row.update(gates(p,dd,np.asarray(row['x']),z,a));row['qualification_scope']='diagnostic omission/prior/start test; not approved removal or independent identity validation'
                row['fully_qualified']=bool(row['phase_closed'] and row['optimizer_success'] and row['all_gates_pass'] and not row['lost_ids'])
                write(path,row);pair[a]=row
                print(case,tag,a,round(row['error_m'],1),'phase',row['phase_closed'],'gates',row['all_gates_pass'],'sec',round(time.monotonic()-began),flush=True)
            write(out/(tag+'.json'),pair)
        write(out/'completion.json',dict(status='complete',seconds=time.monotonic()-began))
    except Exception as exc:
        write(out/'completion.json',dict(status='incomplete',reason=repr(exc),seconds=time.monotonic()-began));raise

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case',choices=CASES);ap.add_argument('--mode',choices=['all','audit','fits'],default='all');a=ap.parse_args();run(a.case,a.mode)
