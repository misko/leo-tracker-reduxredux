"""Bounded, read-only DS26 diagnostics; no changes to published ownership."""
import argparse, copy, csv, hashlib, json, time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from algo06_science.common import read, write, reconstruct
from algo06_science.position import family_score
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import cached
from phase_reference_checks import phase_refresh
from prototype_dsx01_continuous_position import latlon, CENTER
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

ROOT=Path(__file__).resolve().parent
INPUT=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds26_ds27_causal_variants/inputs')
CASES=['DS26-0203','DS26-0070','DS26-0251','DS26-0034']
SITE=(37.849061591561885,-122.48574968092912)
SITE_X=np.array([(SITE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),(SITE[0]-CENTER[0])*111])
ARMS=('c0','fitted_c')

def error(x):
    a,b=np.deg2rad(latlon(x)),np.deg2rad(SITE)
    h=np.sin((a[0]-b[0])/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin((a[1]-b[1])/2)**2
    return float(6371008.8*2*np.arcsin(np.sqrt(h)))

def derivatives(fun,x,h=.05):
    eye=np.eye(2)*h;v=fun(x);g=np.zeros(2);H=np.zeros((2,2))
    for i in range(2):
        plus,minus=fun(x+eye[i]),fun(x-eye[i]);g[i]=(plus-minus)/(2*h);H[i,i]=(plus-2*v+minus)/h**2
    H[0,1]=H[1,0]=(fun(x+eye[0]+eye[1])-fun(x+eye[0]-eye[1])-fun(x-eye[0]+eye[1])+fun(x-eye[0]-eye[1]))/(4*h*h)
    return g,H

def residual_stats(t,r):
    t=np.asarray(t);r=np.asarray(r);u=t-t.mean()
    return dict(n=len(r),span_s=float(np.ptp(t)),mean_hz=float(r.mean()),rms_hz=float(np.sqrt(np.mean(r*r))),
        slope_hz_s=float(u@r/(u@u)) if u@u else 0.,
        lag1=float(np.corrcoef(r[:-1],r[1:])[0,1]) if len(r)>3 and np.std(r)>0 else None,
        noise={k:v[0].item() for k,v in batch_noise_screen(r[None,:],t).items()})

def build(d,z,arm,reference,omit=None,phase_scale=1.):
    keep=d['keep'].copy();base=d['problems'][arm][0]
    for row,sl in zip(base.rows,base.slices):
        if row['candidate_norad']==omit:keep[sl]=False
    entries=[e for e in d['entries'] if e['norad']!=omit]
    kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
    model=dict(d['model'],multiplier=d['model']['multiplier']*phase_scale)
    p=make_event_problem(d['scan'],d['node'],keep,arm,reference,d['powers'],d['means'],model,[],**kw)
    attach_event_predictive(p,entries,d['powers'])
    if z['gap_selected']:
        from conditional_satellite_refresh import attach_conditional_satellite_refresh
        pr=read(Path(z['gap_selected']['path'])/'protocol.json')
        conditional=[e['candidate_index'] for e in pr['targets'] if e['norad']!=omit]
        if conditional:attach_conditional_satellite_refresh(p,entries,d['powers'],conditional)
    cached(p)
    dd=dict(d,entries=entries,families=[f for f in d['families'] if f.entries[0]['norad']!=omit])
    return p,dd

def objective(p,d,x):
    c=p.calculate(x)
    return float(c['negative_twice_elbo']+family_score(d['families'],d,p,x)+np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4)

def refit(d,z,arm,start,omit=None,phase_scale=1.,rounds=5):
    old=d['problems'][arm][0];reference=old.reference.copy();x=np.array(start);history=[];began=time.monotonic()
    for epoch in range(rounds):
        p,dd=build(d,z,arm,reference,omit,phase_scale)
        opt=minimize(lambda v:objective(p,dd,v),x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
            options=dict(maxiter=35,maxfun=140,eps=.001,ftol=1e-10,gtol=1e-4,maxls=15))
        x=opt.x;updated,check=phase_refresh(p.state(x)['phases'][p.labels],reference,limit_s=30)
        history.append(dict(success=bool(opt.success),message=str(opt.message),nfev=opt.nfev,x=x.copy(),**check))
        if check['phase_change_s']<=.01:break
        if epoch<rounds-1:reference=updated
    c=p.calculate(x)
    return dict(x=x,latlon=latlon(x),error_m=error(x),objective=objective(p,dd,x),
        rms_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][p.keep]**2))),history=history,
        reference=p.reference,active_points=int(p.keep.sum()),seconds=time.monotonic()-began,
        phase_closed=check['phase_change_s']<=.01,optimizer_success=bool(opt.success),
        boundary=bool(np.any(abs(x)>12.49)),diagnostic_only=True,omitted_norad=omit,phase_scale=phase_scale)

def audit(case):
    out=ROOT/case;out.mkdir(parents=True,exist_ok=True);z=read(INPUT/(case+'.json'));d=reconstruct(z)
    write(out/'replay.json',d['replay_checks']);rows=[];arms={}
    for arm,(p,x) in d['problems'].items():
        c=p.calculate(x);s=p.state(x);fun=lambda v:objective(p,d,v)
        g,H=derivatives(fun,x);ev,vec=np.linalg.eigh(H)
        reference,check=phase_refresh(s['phases'][p.labels],p.reference,limit_s=30)
        active=sorted({r['candidate_norad'] for r,sl in zip(p.rows,p.slices) if p.keep[sl].any()}|{e['norad'] for e in d['entries']}|{e['norad'] for f in d['families'] for e in f.entries})
        family=[]
        for n in active:
            q,dd=build(d,z,arm,p.reference,omit=n);gf,_=derivatives(lambda v:objective(q,dd,v),x)
            shift=-np.linalg.pinv(H)@gf
            family.append(dict(norad=n,gradient_after_omission=gf,local_predicted_shift_km=shift,shift_norm_km=float(np.linalg.norm(shift)),
                curved_points=sum(int(p.keep[sl].sum()) for r,sl in zip(p.rows,p.slices) if r['candidate_norad']==n),
                associated_points=sum(v==n for v in z['baseline_owners'][arm].values())))
        for k,(r,i,sl) in enumerate(zip(p.rows,p.members,p.slices)):
            use=p.keep[sl];t=p.scan.tracks[i]
            if not use.any():continue
            rr=c['conditional_residual_hz'][sl][use];tt=t['times'][use]
            row=dict(arm=arm,component=r['component'],norad=r['candidate_norad'],receiver=t['receiver'],channel=t['channel'],pieces=len(t['pieces']),
                phase_s=float(s['phases'][r['candidate_index']]),phase_prior_sigma_s=float(p.phase_sigma[p.labels.index(r['candidate_index'])]),
                phase_prior_mean_s=float(d['means'][p.labels.index(r['candidate_index'])]),noise_precision=float(c['noise_precision'][k]),
                **residual_stats(tt,rr))
            rows.append(row)
        np.savez_compressed(out/(arm+'-native-fit.npz'),times=p.flat_times,values=p.values,keep=p.keep,residual=c['conditional_residual_hz'],
            orbit=p.q*c['frequency'],radio_adjusted=p.values-c['conditional_residual_hz'],coefficient=c['coefficient'],phase=s['phases'],beta=s['beta'],smooth=s['smooth'])
        # This fixed-association surface is a diagnostic, not reassociation.
        grid=np.linspace(-12.5,12.5,11);surface=np.array([[fun(np.array([e,n])) for e in grid] for n in grid])
        line=[dict(fraction=float(t),x=x+t*(SITE_X-x),objective=fun(x+t*(SITE_X-x))) for t in np.linspace(0,1,17)]
        arms[arm]=dict(x=x,latlon=latlon(x),error_m=error(x),objective=fun(x),gradient=g,hessian=H,eigenvalues=ev,eigenvectors=vec,
            phase_reference_check=check,beta=s['beta'],phase_sigma_s=p.phase_sigma,phase_prior_means_s=d['means'],
            family_influence=family,grid=grid,surface=surface,oracle_line=line,truth_objective=fun(SITE_X),
            decomposition={k:c[k] for k in ['quadratic','logvolume','gamma_cost','normalization_constant','negative_twice_elbo','precision_iterations','final_log_precision_change'] if k in c})
        print(case,arm,'audit',error(x),'families',len(active),'phase change',check['phase_change_s'],flush=True)
    write(out/'track_residuals.json',rows)
    write(out/'audit.json',dict(case=case,replay=d['replay_checks'],arms=arms,scan_receipt=z['scan_receipt'],
        input_sha256=hashlib.sha256((INPUT/(case+'.json')).read_bytes()).hexdigest(),
        selected_kind=z['selected']['kind'] if z['selected'] else ('gap_conditional' if z['gap_selected'] else 'baseline'),
        notes='Family influence is local sensitivity, not identity evidence. Oracle line uses evaluation truth only as a diagnostic. Grid freezes phase references and associations.'))

def fits(case):
    out=ROOT/case;z=read(INPUT/(case+'.json'));d=reconstruct(z);a=read(out/'audit.json')
    rank={}
    for arm in ARMS:
        for f in a['arms'][arm]['family_influence']:rank[f['norad']]=rank.get(f['norad'],0)+f['shift_norm_km']
    selected=sorted(rank,key=lambda n:(-rank[n],n))[:4]
    # Explicitly test deletion of a previously recovered family as a mechanism control.
    for f in d['families']:
        n=f.entries[0]['norad']
        if n not in selected:selected.append(n)
    if z['gap_selected']:
        n=z['gap_selected']['identity']['norad']
        if n not in selected:selected.append(n)
    write(out/'fit-plan.json',dict(selected=selected,rank=rank,ranking='summed c-arm local omission displacement; no GPS selection',rounds=5,maxiter=35,maxfun=140))
    tests=[('continue',None,1.,'saved'),('regional_center',None,1.,'center'),('phase_sigma_x2',None,2.,'saved')]+[(f'omit_{n}',n,1.,'saved') for n in selected]
    for tag,n,scale,start in tests:
        target=out/(tag+'.json')
        if target.exists():continue
        pair={}
        for arm in ARMS:
            pair[arm]=refit(d,z,arm,np.zeros(2) if start=='center' else d['problems'][arm][1],n,scale)
            write(out/(tag+'-'+arm+'.json'),pair[arm]);print(case,tag,arm,round(pair[arm]['error_m'],1),pair[arm]['phase_closed'],flush=True)
        write(target,pair)

def validation(case):
    from probe_algo03_feasible_recovery import gate_slacks
    from audit_explicit_phase_endpoint import exact_gate_replay
    out=ROOT/case;z=read(INPUT/(case+'.json'));d=reconstruct(z);result=[]
    trials=[('published',None)]+[(p.stem,read(p)) for p in sorted(out.glob('*.json'))
        if p.stem in ['continue','regional_center','phase_sigma_x2'] or p.stem.startswith(('omit_','extended_')) and not p.stem.endswith(('-c0','-fitted_c'))]
    for tag,pair in trials:
        for arm in ARMS:
            if pair is None:p,x=d['problems'][arm];dd=d
            else:
                row=pair[arm];x=np.array(row['x']);p,dd=build(d,z,arm,np.array(row['reference']),row['omitted_norad'],row['phase_scale'])
            slacks=gate_slacks(p,x,dd['entries']);bad={k:v for k,v in slacks.items() if v<0}
            exact=[]
            if tag=='published':
                for j in sorted({r['candidate_index'] for r,sl in zip(p.rows,p.slices) if p.keep[sl].any()}):
                    p.explicit_phase_family=j;v=exact_gate_replay(p,x,dd['entries']);exact.append(dict(norad=int(p.scan.norads[j]),
                        all_pass=v['all_pass'],minimum_slack=v['minimum_slack'],maximum_linearization_difference_hz=v['maximum_linearization_difference_hz']))
                del p.explicit_phase_family
            c=p.calculate(x);begin=p.hardware.shape[1]+p.smooth.shape[1];state=p.state(x)
            families=[]
            for local,j in enumerate(p.labels):
                if not any(r['candidate_index']==j and p.keep[sl].any() for r,sl in zip(p.rows,p.slices)):continue
                orb=c['coefficient'][begin+len(p.labels)+3*p.supported.index(j):begin+len(p.labels)+3*p.supported.index(j)+3] if j in p.supported else []
                families.append(dict(norad=int(p.scan.norads[j]),phase_s=float(state['phases'][j]),phase_prior_mean_s=float(d['means'][local]),
                    phase_sigma_s=float(p.phase_sigma[local]),phase_standardized=float(c['latent_coefficient'][begin+local]),
                    phase_prior_precision=float(c['coefficient_prior_precision'][begin+local]),orbital_standardized=orb))
            result.append(dict(trial=tag,arm=arm,all_base_gates_pass=not bad,minimum_gate_slack=min(slacks.values()),failed_gates=bad,
                exact_orbit_checks=exact,family_nuisance=families,coefficients=c['coefficient'],
                objective=objective(p,dd,x),error_m=error(x),active_points=int(p.keep.sum())))
            print(case,'gates',tag,arm,len(bad),flush=True)
    write(out/'gate_validation.json',result)

def extended(case):
    out=ROOT/case;z=read(INPUT/(case+'.json'));d=reconstruct(z)
    targets={'DS26-0070':[None,62320],'DS26-0203':[67935]}.get(case,[])
    for n in targets:
        pair={a:refit(d,z,a,d['problems'][a][1],omit=n,rounds=15) for a in ARMS}
        write(out/('extended_'+('continue' if n is None else 'omit_'+str(n))+'.json'),pair)
        print(case,'extended',n,[(a,r['error_m'],r['phase_closed']) for a,r in pair.items()],flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['audit','fits','validation','extended']);ap.add_argument('case',choices=CASES);args=ap.parse_args()
    globals()[args.mode](args.case)
