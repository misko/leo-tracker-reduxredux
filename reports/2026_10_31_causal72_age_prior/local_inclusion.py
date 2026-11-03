"""Conditional local position probe of newly nominated older-TLE families.

Keeps incumbent observations, weights and priors identical. A passed local
probe is not independent identity qualification or production authorization.
"""
import argparse
import copy
import time
import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm,t as student
from sgp4.api import Satrec
from run import ROOT,SOURCE,read,write
from evidence import age_penalty
from diagnose_all_large_tracks import context
from predictive_new_family import NewFamily,resolution_audit
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from phase_reference_checks import phase_refresh
from debug_fast_graph_unassociated import memberships
from leo.sky.propagation import ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states
from audit_explicit_phase_endpoint import exact_gate_replay
from leo.analysis.research.predictive_track import phase_resolution_agreement


def run(case):
    started=time.monotonic();folder=ROOT/'local_inclusion'/case;folder.mkdir(parents=True,exist_ok=True)
    proposed=[]
    for f in (ROOT/'cases'/case).glob('*.json'):
        z=read(f);arms={s['arm']:s for s in z['summaries'] if s['policy']=='72_age_scaled_recency24'}
        if all(s['winner']['age_h']>48 for s in arms.values()) and len({s['winner']['norad'] for s in arms.values()})==1:
            proposed.append((z,arms))
    if len(proposed)!=1:raise ValueError('Require one automatically nominated older family for bounded probe')
    z,arms=proposed[0];source=z['source'];n=arms['c0']['winner']['norad']
    if any(any(f['norad']!=n for f in s['training_fold_winners']) for s in arms.values()):
        raise ValueError('Nomination not stable over grouped conditional validation')
    inv=read(source['inventory_path']);d=context(inv);scan=d['scan'];baseline={}
    for arm,(p,x) in d['problems'].items():
        if not np.allclose(x,z['positions'][arm],rtol=0,atol=1e-7):raise ValueError('Published endpoint differs from incumbent replay')
        _,_,ids,owners=memberships(p,x,d['entries']);baseline[arm]=dict(ids=ids,owners=owners,x=x,reference=p.reference.copy())
    if n in scan.norads:raise ValueError('Expected genuinely excluded catalogue identity')
    record=read(SOURCE/'causal72.json')['scans'][case]['elements'][str(n)]
    age=(scan.receipt['cutoff_utc_ns']-record['element_epoch_utc_ns'])/3.6e12
    if not 48<age<=72 or record['collected_utc_ns']>scan.receipt['cutoff_utc_ns']:raise ValueError('Invalid causal vintage')
    j=len(scan.norads);cat=ElementSetCatalogue((str(n),),(n,),(Satrec.twoline2rv(*record['lines']),))
    pos,vel,good=ecef_states(cat,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
    if not good.all():raise ValueError('Propagation failed')
    scan.norads=np.r_[scan.norads,n]
    scan.sky=dict(scan.sky,position_km=np.concatenate([scan.sky['position_km'],pos]),
                  velocity_km_s=np.concatenate([scan.sky['velocity_km_s'],vel]),
                  phase_sigma_s=np.r_[scan.sky['phase_sigma_s'],1.])
    scan.elements[str(n)]=dict(lines=record['lines'],provenance={k:v for k,v in record.items() if k!='lines'})
    tr=scan.tracks[source['track_index']]
    if set(source['observation_ids'])!=set(tr['observation_ids']):raise ValueError('Only intact native source supported here')
    if any(b['ids'].intersection(source['observation_ids']) for b in baseline.values()):raise ValueError('Target already owned')
    aliases={s['winner']['alias'] for s in arms.values()}
    if len(aliases)!=1:raise ValueError('c arms disagree on alias')
    entry=dict(track_index=source['track_index'],component=tr['key'],candidate_index=j,norad=n,
               alias=next(iter(aliases)),points=len(tr['times']),observation_ids=tr['observation_ids'])
    family=NewFamily(scan,[entry],d['model'],phase_step=.1)
    scaled=copy.copy(family);sigma=family.receipt['phase_prior_sigma_s']*max(1.,age/24.)
    mu=family.receipt['phase_prior_mean_s'];nu=family.receipt['phase_prior_nu']
    scaled.distribution=norm(loc=mu,scale=sigma) if nu is None else student(nu,loc=mu,scale=sigma)
    scaled.logprior=scaled.distribution.logpdf(scaled.phases);scaled.logprior[[0,-1]]-=np.log(2)
    scaled.receipt=dict(family.receipt,phase_prior_sigma_s=sigma,experimental_age_scale=max(1.,age/24.))
    write(folder/'protocol.json',dict(case=case,norad=n,target=entry,age_h=age,original_prior=family.receipt,scaled_prior=scaled.receipt,
          variants=['control','72_original_physical_prior','72_age_scaled_physical_prior'],start='published incumbent endpoint per arm',
          fixed_associations=True,maximum_phase_rounds=3,maximum_evaluations_per_round=100,box_width_km=25,
          causal_source=record,baseline_objective_replay=d['replay'],GPS_used=False,
          limits='Local conditional probe, not blind reassociation; randomized nomination conditional on old full-data shortlist; no production acceptance'))
    result={}
    for variant,f in [('control',None),('72_original_physical_prior',family),('72_age_scaled_physical_prior',scaled)]:
        pair={}
        for arm in ['c0','fitted_c']:
            x=baseline[arm]['x'].copy();reference=baseline[arm]['reference'].copy();history=[]
            for epoch in range(3):
                if time.monotonic()-started>600:raise TimeoutError('600-second bounded local probe exhausted')
                p=make_event_problem(scan,d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[])
                attach_event_predictive(p,d['entries'],d['powers']);cached(p)
                def objective(v):
                    if time.monotonic()-started>600:raise TimeoutError('600-second local probe cap')
                    c=p.calculate(v);penalty=np.sum(np.minimum(0,c['elevation'][p.keep])**2)/4
                    return c['negative_twice_elbo']+penalty+(0 if f is None else f.evaluate(p,v,d['powers'],d['entries']))
                opt=minimize(objective,x,method='L-BFGS-B',bounds=[(-12.5,12.5)]*2,
                             options=dict(maxiter=30,maxfun=100,eps=.001,ftol=1e-10,gtol=1e-4,maxls=15))
                x=opt.x;phase,check=phase_refresh(p.state(x)['phases'][p.labels],reference)
                history.append(dict(epoch=epoch,success=bool(opt.success),message=str(opt.message),nfev=opt.nfev,**check))
                if check['phase_change_s']<=.01:break
                if epoch<2:reference=phase
            row=summary(p,x,d['entries']);_,_,ids,owners=memberships(p,x,d['entries'])
            changed=[o for o,n0 in baseline[arm]['owners'].items() if owners.get(o)!=n0]
            labels={r['candidate_index'] for r,sl in zip(p.rows,p.slices) if p.keep[sl].any()}|{e['candidate_index'] for e in d['entries']}
            exact=[]
            for label in sorted(labels):
                p.explicit_phase_family=label;exact.append(dict(norad=int(scan.norads[label]),**exact_gate_replay(p,x,d['entries'])))
            if hasattr(p,'explicit_phase_family'):del p.explicit_phase_family
            detail=None
            if f is not None:
                detail=f.evaluate(p,x,d['powers'],d['entries'],details=True)
                row['incumbent_objective']=row['negative_twice_elbo'];row['negative_twice_elbo']+=detail['negative_twice_log_density']
                row['target']=detail
                row['continuous_target']=f.evaluate(p,x,d['powers'],d['entries'],details=True,refine_phase=True)
                finer=[]
                for step in [.05,.025]:
                    ff=NewFamily(scan,[entry],d['model'],phase_step=step)
                    if variant=='72_age_scaled_physical_prior':
                        ff.distribution=scaled.distribution
                        ff.logprior=ff.distribution.logpdf(ff.phases);ff.logprior[[0,-1]]-=np.log(2)
                    finer.append(ff)
                offsets=np.array([[0,0],[.025,0],[-.025,0],[0,.025],[0,-.025]])
                scores=np.array([[ff.evaluate(p,x+offset,d['powers'],d['entries']) for ff in [f]+finer] for offset in offsets])
                row['quadrature']=dict(steps_s=[.1,.05,.025],scores=scores,**phase_resolution_agreement(scores))
                row['score_with_recency24']=row['negative_twice_elbo']+age_penalty(age)
                row['proposed_added_points']=entry['points']
            checks=dict(optimizer=bool(opt.success),phase=history[-1]['phase_change_s']<=.01,
                        incumbent_exact_orbits=all(q['all_pass'] for q in exact),existing_owners_preserved=not changed,
                        target=True if detail is None else all(g['compatible'] for g in detail['gates']),
                        target_continuous=True if detail is None else all(g['compatible'] for g in row['continuous_target']['gates']),
                        quadrature=True if detail is None else row['quadrature']['local_agreement'],
                        target_phase_interior=True if detail is None else detail['phase_boundary_mass']<.01)
            row.update(history=history,checks=checks,all_checked_gates_pass=all(checks.values()),
                       exact_incumbent_orbits=exact,changed_incumbent_ids=changed,
                       baseline_associated_points=len(baseline[arm]['ids']),baseline_endpoint_km=baseline[arm]['x'],
                       production_added_points=0,independent_identity_validation_complete=False)
            pair[arm]=row
            write(folder/(variant+'-'+arm+'.json'),row)
            print(case,variant,arm,x.tolist(),checks,round(time.monotonic()-started,1),flush=True)
        result[variant]=pair;write(folder/'result.json',result)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case');a=ap.parse_args();run(a.case)
