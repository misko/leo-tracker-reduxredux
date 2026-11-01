"""Bounded causal family reconsideration and influence stress tests.

This adapter imports numerical helpers from the frozen preceding investigation.
No production policy is changed. Truth is used only after fitting, for errors.
"""
import argparse, copy, hashlib, json, sys, time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

OUT=Path(__file__).resolve().parent
PRIOR=OUT.parent/'2026_11_01_ds26_outlier_root_cause'
sys.path.insert(1,str(PRIOR))
from diagnose import INPUT, ARMS, CASES, read, write, reconstruct, build, objective, error
from family_debug import SUSPECT
from phase_reference_checks import phase_refresh
from probe_algo03_feasible_recovery import gate_slacks
from audit_explicit_phase_endpoint import exact_gate_replay
from algo06_science.position import family_score
from debug_fast_graph_unassociated import memberships
from inactive_graph_fragment import original_graph_view
from ds23_feasible_position import feasible_fit
from prototype_dsx01_continuous_position import latlon

def age_penalty(age_h, policy):
    """Once per unique satellite, in negative-twice-log-prior units."""
    if not np.isfinite(age_h) or age_h<0: raise ValueError('finite nonnegative age required')
    if policy=='none':return 0.
    if policy=='linear24':return 2*np.log(2)*age_h/24
    if policy=='quadratic24':return (age_h/24)**2
    if policy=='grace48':return (max(0.,age_h-48)/12)**2
    if policy=='hard48':return 0. if age_h<=48 else float('inf')
    raise ValueError(policy)

def nominees(case):
    f=read(PRIOR/case/'family_diagnostic.json');nums={SUSPECT[case]}
    for a in ARMS:
        rows=sorted([r for r in f['results'] if r['arm']==a and r['regime']=='causal' and r['calibration']=='family_omitted' and r['split']=='all' and r['level']=='small_rate'],key=lambda r:r['score'])
        nums.update(r['norad'] for r in rows[:2])
    return sorted(nums)

def candidate(d,z,case,new,weight):
    old=SUSPECT[case];dd=dict(d,node=copy.deepcopy(d['node']),entries=copy.deepcopy(d['entries']),powers=d['powers'].copy(),problems={})
    base=d['problems']['fitted_c'][0]
    for k,r in enumerate(base.rows):
        if r['candidate_norad']==old:dd['powers'][k]*=weight
    if new==old:
        dd['problems']=d['problems'];return dd
    jold=list(d['scan'].norads).index(old)
    if new not in d['scan'].norads:
        from sgp4.api import Satrec
        from leo.sky.propagation import ElementSetCatalogue
        from analyze_dsx01_fixed_site import ecef_states
        record=read(PRIOR/case/'tle-ledger.json')['causal'][str(new)]
        scan=copy.copy(d['scan']);jnew=len(scan.norads)
        cat=ElementSetCatalogue((str(new),),(new,),(Satrec.twoline2rv(*record['lines']),))
        pos,vel,good=ecef_states(cat,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
        if not good.all():raise ValueError('causal propagation failed')
        scan.norads=np.r_[scan.norads,new]
        scan.sky=dict(scan.sky,position_km=np.concatenate([scan.sky['position_km'],pos]),velocity_km_s=np.concatenate([scan.sky['velocity_km_s'],vel]),phase_sigma_s=np.r_[scan.sky['phase_sigma_s'],1.])
        scan.elements=dict(scan.elements,**{str(new):dict(lines=record['lines'],provenance={k:v for k,v in record.items() if k!='lines'})})
        dd['scan']=scan;dd['node']['seed']['state']['phases']=np.r_[dd['node']['seed']['state']['phases'],0.]
    else:jnew=list(d['scan'].norads).index(new)
    f=read(PRIOR/case/'family_diagnostic.json')
    nomination=next(r for r in f['results'] if r['arm']=='fitted_c' and r['regime']=='causal' and r['calibration']=='family_omitted' and r['split']=='all' and r['level']=='small_rate' and r['norad']==new)
    aliases={t['key']:int(a) for t,a in zip(f['tracks'],nomination['aliases'],strict=True)}
    for r in dd['node']['seed']['rows']:
        if r['candidate_norad']==old:r.update(candidate_norad=new,candidate_index=jnew)
    for k,r in enumerate(base.rows):
        if r['component'] in aliases:dd['node']['aliases'][k]=aliases[r['component']]
    for e in dd['entries']:
        if e['norad']==old:e.update(norad=new,candidate_index=jnew)
    labels=sorted((set(base.labels)-{jold})|{jnew});means=dict(zip(base.labels,d['means']))
    dd['means']=np.array([means.get(j,0.) for j in labels])
    for a in ARMS:
        p,x=d['problems'][a];dd['problems'][a]=(p,x)
        refs=dict(zip(p.labels,p.reference))
        ref=np.array([refs.get(j,nomination['phase_s'] if j==jnew else 0.) for j in labels])
        p,_=build(dd,z,a,ref);dd['problems'][a]=(p,x)
    return dd

def fit(d,z,arm,start,constrained=False,rounds=15):
    reference=d['problems'][arm][0].reference.copy();x=np.asarray(start);history=[];tic=time.monotonic()
    for epoch in range(rounds):
        p,dd=build(d,z,arm,reference)
        fun=lambda v:objective(p,dd,v)
        if constrained:
            opt=feasible_fit(fun,lambda v:list(gate_slacks(p,v,dd['entries']).values()),x,[-12.5]*2,[12.5]*2,iterations=40)
            x=np.asarray(opt['parameters']);success=opt['solver_success'];message=opt['solver_message'];nfev=opt['evaluations']
        else:
            opt=minimize(fun,x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,options=dict(maxiter=35,maxfun=140,eps=.001,ftol=1e-10,gtol=1e-4,maxls=15))
            x=opt.x;success=bool(opt.success);message=str(opt.message);nfev=int(opt.nfev)
        updated,check=phase_refresh(p.state(x)['phases'][p.labels],reference,limit_s=30)
        history.append(dict(x=x,success=success,message=message,nfev=nfev,**check))
        if check['phase_change_s']<=.01:break
        if epoch<rounds-1:reference=updated
    c=p.calculate(x);slacks=gate_slacks(p,x,dd['entries']);bad={k:v for k,v in slacks.items() if v<0}
    exact=[]
    for j in sorted({r['candidate_index'] for r,sl in zip(p.rows,p.slices) if p.keep[sl].any()}):
        p.explicit_phase_family=j;v=exact_gate_replay(p,x,dd['entries']);exact.append(dict(norad=int(p.scan.norads[j]),all_pass=v['all_pass'],failed={k:v for k,v in v['all_gate_slacks'].items() if v<0},maximum_difference_hz=v['maximum_linearization_difference_hz']))
    if hasattr(p,'explicit_phase_family'):del p.explicit_phase_family
    _,fd=family_score(dd['families'],dd,p,x,details=True)
    mixture_pass=all(g['compatible'] for f in fd for g in f['gates'])
    _,_,_,owners=memberships(original_graph_view(p,len(p.scan.index)),x,dd['entries'])
    for f in dd['families']:
        for e in f.entries:owners.update({o:e['norad'] for o in e['observation_ids']})
    before=z['baseline_owners'][arm]
    lost=[o for o in before if o not in owners];added=[o for o in owners if o not in before]
    changed=[o for o,n in before.items() if o in owners and owners[o]!=n]
    allpass=not bad and all(r['all_pass'] for r in exact) and mixture_pass
    params=[];begin=p.hardware.shape[1]+p.smooth.shape[1]
    for k,j in enumerate(p.labels):
        orb=c['coefficient'][begin+len(p.labels)+3*p.supported.index(j):begin+len(p.labels)+3*p.supported.index(j)+3] if j in p.supported else []
        params.append(dict(norad=int(p.scan.norads[j]),phase_s=float(p.state(x)['phases'][j]),phase_sigma_s=float(p.phase_sigma[k]),orbital_standardized=orb))
    tracks=[]
    for r,i,sl in zip(p.rows,p.members,p.slices):
        use=p.keep[sl]
        if not use.any():continue
        t=p.scan.tracks[i];tracks.append(dict(component=r['component'],norad=r['candidate_norad'],receiver=t['receiver'],channel=t['channel'],times_s=t['times'][use],values_hz=p.values[sl][use],residual_hz=c['conditional_residual_hz'][sl][use],observation_ids=[o for o,u in zip(t['observation_ids'],use) if u]))
    return dict(x=x,latlon=latlon(x),error_m=error(x),objective=fun(x),rms_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),
        history=history,reference=reference,phase_closed=check['phase_change_s']<=.01,optimizer_success=success,all_gates_pass=allpass,
        failed_gates=bad,exact=exact,mixture_gates_pass=mixture_pass,active_points=int(p.keep.sum()),seconds=time.monotonic()-tic,
        lost_ids=lost,added_ids=added,reassigned_ids=changed,proposed_owners=owners,parameters=params,tracks=tracks,
        qualified=bool(allpass and check['phase_change_s']<=.01 and success and not lost),
        qualification_scope='RF/phase/optimizer/orbit/ownership screening; not independent identity validation or complete production acceptance')

def run(case):
    out=OUT/case;out.mkdir(parents=True,exist_ok=True);z=read(INPUT/(case+'.json'));d=reconstruct(z);old=SUSPECT[case]
    write(out/'replay.json',d['replay_checks'])
    cavity=PRIOR/case/f'extended_omit_{old}.json'
    if not cavity.exists():cavity=PRIOR/case/f'omit_{old}.json'
    starts={'published':d['problems']['fitted_c'][1],'family_omitted':np.array(read(cavity)['fitted_c']['x'])}
    # Identical two starts for both c arms and every identity; no evaluation-site start.
    for new in nominees(case):
        for weight in (1.,.5,.25):
            dd=candidate(d,z,case,new,weight)
            for constrained in (False,True):
                # Constrained position tests isolate identity changes at full weight.
                if constrained and weight!=1.:continue
                tag=f'{new}-w{weight:g}-'+('constrained' if constrained else 'free')
                target=out/(tag+'.json')
                if target.exists():continue
                rows=[]
                for a in ARMS:
                    for start_name,start in starts.items():
                        r=fit(dd,z,a,start,constrained)
                        r.update(arm=a,start=start_name);rows.append(r)
                        print(case,tag,a,start_name,round(r['error_m']/1000,3),r['qualified'],len(r['failed_gates']),round(r['seconds'],1),flush=True)
                write(target,dict(case=case,old_norad=old,new_norad=new,weight=weight,constrained=constrained,rows=rows))

def freeze():
    sources=[Path(__file__),PRIOR/'diagnose.py',PRIOR/'family_debug.py']
    receipts={}
    for case in CASES:
        inputs=[INPUT/(case+'.json'),PRIOR/case/'tle-ledger.json',PRIOR/case/'family_diagnostic.json']
        receipts[case]=dict(target=SUSPECT[case],nominees=nominees(case),hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
    write(OUT/'protocol.json',dict(cases=receipts,code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        candidate_policy='reuse prior full causal discovery, top two family-omitted RF nominees union across c arms; bounded shortlist, not new exhaustive search',
        weights=[1,.5,.25],age_policies=['none','linear24','quadratic24','grace48','hard48'],age_prior_scope='unique satellite once, no per-point age penalty',
        age_definition='hours from element epoch to scan cutoff; collection also <= cutoff',
        starts='same fitted-c published and family-omitted RF positions for every candidate and both c arms',
        priors='unchanged physical/phase priors; missing causal-history candidates use existing fallback; age does not widen nuisance priors',
        fit_budget=dict(phase_rounds=15,phase_tolerance_s=.01,phase_limit_s=30,L_BFGS_maxiter=35,L_BFGS_maxfun=140,SLSQP_maxiter=40),
        box_center=[37.906,-122.545],box_km=25,
        evaluation='four post-hoc outlier stress tests, NOT independent validation; no evaluation truth in nomination/score/starts',
        acceptance='retain all existing points; exact orbit + all existing gates + phase closure + optimizer + owner retention; no relaxation',
        selection='within fixed weight/constrained policy choose RF score among screened candidates, age terms added once per unique affected satellite',
        production_changed=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case',choices=CASES+['freeze']);a=p.parse_args()
    freeze() if a.case=='freeze' else run(a.case)
