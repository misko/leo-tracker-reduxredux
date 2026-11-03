"""Matched conditional position trials with exact incumbent likelihood replay.

At most one new-family target per policy. Existing accepted ownership is a
hard constraint; no incumbent fit term is discarded. With one incumbent
new-family mixture, integrate the pair jointly rather than doubling receiver
information. Existing two-mixture incumbents fail closed at the declared cap.
"""
import argparse,copy,time,sys,os,subprocess
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from scipy.optimize import minimize
from sgp4.api import Satrec
from common import *
from predictive_new_family import NewFamily,resolution_audit
from probe_joint_predictive_families import joint_inputs
from leo.analysis.research.joint_predictive_families import two_family_phase_evidence
from leo.analysis.research.predictive_track import phase_resolution_agreement
from leo.sky.propagation import ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states
from native_predictive_branch import append_branch
from debug_fast_graph_unassociated import memberships
from inactive_graph_fragment import original_graph_view
from phase_reference_checks import phase_refresh
from audit_explicit_phase_endpoint import exact_gate_replay
from leo.analysis.research.retained_track_likelihood import PERIOD,profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from annotate_predictive_only import receiver_design
from prototype_dsx01_continuous_position import latlon

def family_score(families,d,p,x,details=False):
    if not families:return (0.,[]) if details else 0.
    if len(families)==1:
        f=families[0];v=f.evaluate(p,x,d['powers'],d['entries'],details=details,refine_phase=details)
        return (v['negative_twice_log_density'],[v]) if details else v
    if len(families)!=2:raise ValueError('Exact two-family compute cap exceeded')
    joint=two_family_phase_evidence(*joint_inputs(families,p,x,d['powers'],d['entries']))
    if not details:return joint['negative_twice_log_density']
    c=p.curved_calculate(x) if d['entries'] else p.calculate(x);coef=c['coefficient'];rows=[]
    for k,f in enumerate(families):
        phase=float(f.phases[joint['joint_map_indices'][k]]);orb=np.asarray(joint['orbital_map_mean'][k])
        bank={key:value[:1] if key!='time_s' else value for key,value in f.bank.items()}
        modes={key:value[:3] if key!='time_s' else value for key,value in f.modes.items()}
        ff,ee=paired_phase_frequency(bank,f.times,np.zeros(len(f.times),int),np.array([phase]),*latlon(x))
        uu=paired_frequency_modes(bank,modes,f.times,np.zeros(len(f.times),int),np.array([phase]),*latlon(x))
        h=np.concatenate([receiver_design(t['times'],t['rf_hz'],t['receiver'],t['channel'],f.scan.rx_basis[e['track_index']],fitted_c=p.fitted_c) for t,e in zip(f.tracks,f.entries)])
        pred=h@coef[:h.shape[1]]+(ff+uu@orb)*f.q;raw=f.values-pred;diagnostics=[];gates=[]
        for e,tr,sl in zip(f.entries,f.tracks,f.slices):
            v=profile(raw[sl],np.zeros(sl.stop-sl.start),*f.scan.white[e['track_index']],bias_sigma=300)
            noise={a:b[0].item() for a,b in batch_noise_screen(v['innovations'],tr['times']).items()}
            compatible=bool(v['rms'][0]<=450 and abs(v['bias'][0])<=3000 and v['alias'][0]==0 and noise['noise_screen_pass'] and ee[sl].min()>=0)
            gates.append(dict(compatible=compatible,component=e['component'],norad=e['norad']))
            diagnostics.append(dict(times_s=tr['times'],CFO_hz=tr['values'],prediction_CFO_hz=pred[sl]-e['alias']*PERIOD,
                raw_residual_hz=raw[sl],profile_RMS_hz=float(v['rms'][0]),profile_bias_hz=float(v['bias'][0]),noise=noise))
        weights=joint['phase_marginals'][k]
        rows.append(dict(phase_map_s=phase,orbital_posterior_mean=orb,gates=gates,diagnostics=diagnostics,
            phase_boundary_mass=float(weights[abs(f.phases)>=f.phase_limit_s-.1].sum()),joint_not_factorized=True))
    return joint['negative_twice_log_density'],rows

def add_target(d,z,source,winner):
    scan=d['scan'];n=winner['norad'];record=read(ROOT/'catalogues'/(z['case']+'.json'))['elements'][str(n)]
    existing=np.flatnonzero(scan.norads==n)
    if len(existing):j=int(existing[0])
    else:
        j=len(scan.norads);cat=ElementSetCatalogue((str(n),),(n,),(Satrec.twoline2rv(*record['lines']),))
        pos,vel,good=ecef_states(cat,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
        if not good.all():raise ValueError('Candidate propagation failure')
        scan.norads=np.r_[scan.norads,n]
        scan.sky=dict(scan.sky,position_km=np.concatenate([scan.sky['position_km'],pos]),velocity_km_s=np.concatenate([scan.sky['velocity_km_s'],vel]),phase_sigma_s=np.r_[scan.sky['phase_sigma_s'],1.])
        scan.elements=dict(scan.elements,**{str(n):dict(lines=record['lines'],provenance={k:v for k,v in record.items() if k!='lines'})})
    track=scan.tracks[source['track_index']];ix=np.asarray(source['source_local_indices']);ids=source['observation_ids']
    if list(track['observation_ids'])==ids:i=source['track_index']
    else:
        observations=read(Path(z['native_path'])/'observations.json');lookup={o['observation_id']:o for o in observations}
        y=track['values'][ix];lifts=np.rint((y-np.array([lookup[o]['measured_cfo_hz'] for o in ids]))/PERIOD).astype(int)
        branch=dict(branch_id=source['fragment_id'],observation_ids=ids,times_s=track['times'][ix],values_hz=y,alias_lifts=lifts,
            receiver=track['receiver'],channel=track['channel'],rf_hz=track['rf_hz'],quality_status='unchanged_gap_fragment',pieces=track['pieces'],RMS_hz=track['residual_rms_hz'])
        scan,i=append_branch(scan,branch,observations,set(z['baseline_owners']['c0'])|set(z['baseline_owners']['fitted_c']));d['scan']=scan
    entry=dict(track_index=i,component=scan.tracks[i]['key'],candidate_index=j,norad=n,alias=winner['alias'],points=len(ids),observation_ids=ids)
    return entry

def prediction_scan(scan,bound):
    """Extend propagation only in a private predictive view, never calibration."""
    if bound<=15:return scan
    view=copy.copy(scan);grid=np.arange(min(-40.,min(scan.sky['time_s'])),max(341.,max(scan.sky['time_s'])+1))
    numbers=tuple(map(int,scan.norads))
    cat=ElementSetCatalogue(tuple(map(str,numbers)),numbers,tuple(Satrec.twoline2rv(*scan.elements[str(n)]['lines']) for n in numbers))
    p,v,good=ecef_states(cat,scan.receipt['origin_utc_ns'],grid)
    if not good.all():raise ValueError('Expanded private orbit propagation failure')
    view.sky=dict(scan.sky,time_s=grid,position_km=p,velocity_km_s=v)
    for attr in ('causal_uncertainty_modes','previous_shape_cache','reference_motion_derivatives','mean_motion_derivatives'):
        if hasattr(view,attr):setattr(view,attr,{})
    return view

def fit_pair(z,d,extra,tag,deadline):
    pair={};allfamilies=d['families']+([extra] if extra else [])
    for arm in ARMS:
        oldp,x=d['problems'][arm];x=x.copy();reference=oldp.reference.copy();history=[]
        for epoch in range(3):
            p=d['factory'](arm,reference)
            def objective(v):
                if time.monotonic()>deadline:raise TimeoutError('Bounded conditional position trial exhausted')
                c=p.calculate(v)
                return c['negative_twice_elbo']+np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4+family_score(allfamilies,d,p,v)
            opt=minimize(objective,x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
                 options=dict(maxiter=30,maxfun=100,eps=.001,ftol=1e-10,gtol=1e-4,maxls=15))
            x=opt.x;phase,check=phase_refresh(p.state(x)['phases'][p.labels],reference,limit_s=30)
            history.append(dict(success=bool(opt.success),message=str(opt.message),nfev=int(opt.nfev),**check))
            if check['phase_change_s']<=.01:break
            if epoch<2:reference=phase
        score,details=family_score(allfamilies,d,p,x,details=True)
        _,_,ids,owners=memberships(original_graph_view(p,len(p.scan.index)),x,d['entries'])
        for f in d['families']:
            for e in f.entries:owners.update({o:e['norad'] for o in e['observation_ids']})
        changed=[o for o,n in z['baseline_owners'][arm].items() if owners.get(o)!=n]
        labels={r['candidate_index'] for r,sl in zip(p.rows,p.slices) if p.keep[sl].any()}|{e['candidate_index'] for e in d['entries']}
        exact=[]
        for j in sorted(labels):
            p.explicit_phase_family=j;exact.append(dict(norad=int(p.scan.norads[j]),**exact_gate_replay(p,x,d['entries'])))
        if hasattr(p,'explicit_phase_family'):del p.explicit_phase_family
        # Refine only the newly integrated family; incumbent quadrature is the
        # same sealed numerical model in control and candidate. Joint evidence
        # retains its shared receiver covariance in every refinement.
        quad=dict(local_agreement=True,reason='control has no new quadrature')
        if extra:
            step=extra.receipt['phase_step_s']
            finer=[extra]+[NewFamily(extra.scan,extra.entries,d['model'],phase_step=h,
                     phase_limit_s=extra.phase_limit_s,allow_uncalibrated_label=True) for h in (step/2,step/4)]
            offsets=np.array([[0,0],[.025,0],[-.025,0],[0,.025],[0,-.025]])
            scores=np.array([[family_score(d['families']+[f],d,p,x+v) for f in finer] for v in offsets])
            quad=dict(steps_s=[step,step/2,step/4],scores=scores,**phase_resolution_agreement(scores))
        checks=dict(optimizer=bool(opt.success),phase=history[-1]['phase_change_s']<=.01,
            incumbent_exact_orbits=all(r['all_pass'] for r in exact),existing_owners_preserved=not changed,
            family_residuals=all(g['compatible'] for f in details for g in f['gates']),
            phase_interior=all(f['phase_boundary_mass']<.01 for f in details),quadrature=quad['local_agreement'])
        row=dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),negative_twice_elbo=float(p.calculate(x)['negative_twice_elbo']+score),
            history=history,checks=checks,all_checked_gates_pass=all(checks.values()),family_details=details,
            quadrature=quad,changed_incumbent_ids=changed,incumbent_exact_orbits=exact,
            baseline_associated=len(z['baseline_owners'][arm]),proposed_added_points=extra.entries[0]['points'] if extra else 0,
            phase_reference=p.reference)
        pair[arm]=row;write(ROOT/'position'/z['case']/(tag+'-'+arm+'.json'),row)
    return pair

def one(case):
    began=time.monotonic();z=read(ROOT/'inputs'/(case+'.json'));screen=read(ROOT/'screen'/case/'result.json')
    family_count=2 if z.get('selected') and z['selected']['kind']=='joint' else (1 if z.get('selected') and z['selected']['kind']=='new_family' else 0)
    current={int(n) for n in z['baseline_owners']['fitted_c'].values()}|{int(n) for n in z['baseline_owners']['c0'].values()}
    choices={};decisions={};trials={}
    for policy in POLICIES:
        options=[];excluded=[]
        for t in screen['targets']:
            s=next(s for s in t['summaries'] if s['policy']==policy)
            if not s['screen_pass']:continue
            w=s['arms']['c0']['folds']['full']['winner'];n=w['norad']
            if n in current:excluded.append(dict(fragment_id=t['source']['fragment_id'],norad=n,reason='existing family; shared-family route unchanged'));continue
            if family_count>=2:excluded.append(dict(fragment_id=t['source']['fragment_id'],norad=n,reason='exact joint-family compute cap'));continue
            margin=min(v['margin'] for a in ARMS for v in s['arms'][a]['folds'].values())
            if margin<10:continue
            options.append((margin,t['source']['points'],t['source']['fragment_id'],t['source'],w))
        options.sort(key=lambda v:(-v[0],-v[1],v[2]))
        choices[policy]=options[0] if options else None
        decisions[policy]=dict(excluded=excluded,eligible_proposals=len(options),status='no_qualified_new_family' if not options else 'pending')
    if any(choices.values()):
        d=reconstruct(z)
        control=fit_pair(z,d,None,'control',time.monotonic()+600)
        for policy,option in choices.items():
            if option is None:continue
            _,_,fid,source,winner=option;bound=POLICIES[policy][1];key=f'{fid}-{winner["norad"]}-{bound}'
            if key not in trials:
                # Reconstruct each trial so a rejected addition cannot contaminate
                # any subsequent candidate, c arm, or baseline model.
                dd=reconstruct(z);entry=add_target(dd,z,source,winner)
                try:
                    f=NewFamily(prediction_scan(dd['scan'],bound),[entry],dd['model'],phase_step=.05,phase_limit_s=bound,allow_uncalibrated_label=True)
                    pair=fit_pair(z,dd,f,key,time.monotonic()+600)
                    valid=all(v['all_checked_gates_pass'] for v in pair.values()) and all(v['all_checked_gates_pass'] for v in control.values())
                    trials[key]=dict(status='qualified' if valid else 'rejected',entry=entry,arms=pair,prior=f.receipt)
                except (ValueError,TimeoutError) as e:trials[key]=dict(status='failed_closed',entry=entry,error=str(e))
            decisions[policy].update(status=trials[key]['status'],trial=key,source=source['fragment_id'],norad=winner['norad'])
    else:control=None
    write(ROOT/'position'/case/'result.json',dict(case=case,decisions=decisions,trials=trials,control=control,
          seconds=time.monotonic()-began,conditional_recovery=True,production_changed=False))
    print(case,{k:v['status'] for k,v in decisions.items()},flush=True)

def batch(workers,reverse=False):
    roster=read(ROOT/'protocol.json')['cohort'];results=[];suffix='-reverse' if reverse else ''
    if reverse:roster=roster[::-1]
    def work(z):
        case=z['case'];log=ROOT/'logs'/('position'+suffix+'-'+case+'.log');result=ROOT/'position'/case/'result.json'
        if result.exists():return dict(case=case,status='cached')
        with log.open('w') as f:
            try:
                r=subprocess.run([sys.executable,__file__,'--case',case],stdout=f,stderr=subprocess.STDOUT,timeout=2400,
                     env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
                return dict(case=case,status='complete' if r.returncode==0 else 'failed',returncode=r.returncode,log=str(log))
            except subprocess.TimeoutExpired:return dict(case=case,status='timeout',log=str(log))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(work,z) for z in roster]):
            r=future.result();results.append(r);write(ROOT/('position'+suffix+'-execution.json'),results);print(len(results),r,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case');p.add_argument('--workers',type=int,default=12);p.add_argument('--reverse',action='store_true');a=p.parse_args()
    if a.case:
        import fcntl
        path=ROOT/'locks';path.mkdir(exist_ok=True)
        with (path/('position-'+a.case+'.lock')).open('w') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX)
            if not (ROOT/'position'/a.case/'result.json').exists():one(a.case)
    else:batch(a.workers,a.reverse)
