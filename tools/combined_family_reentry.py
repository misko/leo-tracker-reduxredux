"""General bounded family reentry after active-support recovery; no GPS inputs."""

import argparse
import copy
from functools import partial
import hashlib
from pathlib import Path
import time

import numpy as np
from scipy.linalg import cho_solve

import debug_fast_graph_unassociated as report
from benchmark_graph_covariance import load_case,baseline_pair,support_recovery
from correlated_curve_prediction import conditional,randomized_blocks
from investigate_cohort_priority_tracks import qualifies

ARMS=('c0','fitted_c')


def build(d,keep,arm,reference,target,sigma):
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_history_calibrated_phase import make_problem
    from probe_ds23_frequency_events import cached
    def factory(*args,**kwargs):
        p=make_problem(*args,**kwargs,support_policy=d['support_policy'])
        p.constants[:,target]*=sigma/300.
        return p
    p=make_event_problem(d['scan'],d['node'],keep,arm,reference,d['powers'],d['means'],d['model'],[],base_problem_factory=factory)
    attach_event_predictive(p,d['entries'],d['powers']);return cached(p)


def offers(d,pair):
    p,_=d['problems']['c0'];owned=set().union(*(set(r['proposed_associated_ids']) for r in pair.values()))
    active={r['candidate_index'] for r,sl in zip(p.rows,p.slices) if p.keep[sl].any()}
    active.update(e['candidate_index'] for e in d['entries'])
    result=[]
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices)):
        t=d['scan'].tracks[i]
        if p.keep[sl].any() or row['candidate_index'] in active or owned.intersection(t['observation_ids']):continue
        if len(t['times'])<20 or np.ptp(t['times'])<24:continue
        result.append(dict(row=k,component=t['key'],norad=row['candidate_norad'],points=len(t['times']),span_s=float(np.ptp(t['times']))))
    return sorted(result,key=lambda r:(-r['points'],-r['span_s'],r['component']))


def choose_width(gains,penalty=2*np.log(2)):
    """A wider model must improve held density in each matched c arm."""
    if set(gains)!=set(ARMS) or not all(np.isfinite(v) for v in gains.values()):
        raise ValueError('finite paired predictive gains required')
    return 1000 if all(v>penalty for v in gains.values()) else 300


def predict_width(d,target,sigma,seed):
    p,_=d['problems']['c0'];sl=p.slices[target];t=d['scan'].tracks[p.members[target]]
    train,receipt=randomized_blocks(t['times'],seed=seed)
    keep=d['keep'].copy();keep[sl]=train;held=np.arange(sl.start,sl.stop)[~train];result={}
    for arm,(_,x) in d['problems'].items():
        reference=np.zeros(len(d['means']))
        for _ in range(5):
            q=build(d,keep,arm,reference,target,sigma);c=q.calculate(x)
            phase=np.clip(q.state(x)['phases'][q.labels],-15,15);delta=float(np.max(abs(phase-reference)));reference=phase
        # Held values were never in the normal equations. The posterior
        # covariance includes receiver, orbit, phase and this same curve bias.
        features=c['features'];groups=q.noise_groups[keep]
        weights=d['powers'][groups]*c['noise_precision'][groups]/q.point_noise[keep]**2
        gram=np.diag(c['coefficient_prior_precision'])+features[keep].T@(features[keep]*weights[:,None])
        root=np.linalg.cholesky(gram);design=features[held]
        measurement=q.point_noise[held]**2/max(float(c['noise_precision'][target]),1e-12)
        covariance=np.diag(measurement)+design@cho_solve((root,True),design.T)
        from correlated_curve_prediction import gaussian
        score=gaussian(c['conditional_residual_hz'][held],covariance)
        result[arm]=dict(objective=score['objective'],held_points=len(held),training_points=int(train.sum()),
            held_residual_hz=c['conditional_residual_hz'][held],held_sigma_hz=np.sqrt(np.diag(covariance)),
            final_phase_change_s=delta,noise_precision=float(c['noise_precision'][target]))
    return dict(split=receipt,arms=result)


def select_width(d,target):
    trials={};seen=set()
    p,_=d['problems']['c0'];times=d['scan'].tracks[p.members[target]]['times']
    for seed in (20261029,0,1):
        _,receipt=randomized_blocks(times,seed=seed);key=tuple(receipt['withheld_blocks'])
        if key in seen:continue
        seen.add(key);trials[str(seed)]={str(s):predict_width(d,target,s,seed) for s in (300,1000)}
    gains={a:sum(v['300']['arms'][a]['objective']-v['1000']['arms'][a]['objective'] for v in trials.values()) for a in ARMS}
    convergence=all(r['final_phase_change_s']<=.01 for v in trials.values() for w in v.values() for r in w['arms'].values())
    sigma=choose_width(gains) if convergence else 300
    return dict(selected_sigma_hz=sigma,held_density_gains=gains,extra_selection_penalty=2*np.log(2),
        all_training_phase_fits_converged=convergence,trials=trials,
        fixed_position='preceding accepted RF endpoint, no evaluation coordinates',
        caveat='Empirical Gaussian posterior conditional on fixed graph, identity and baseline calibration; not blind held acquisition')


def fit_pair(d,target,sigma,*,start=(0.,0.),constrained_from=None,restore=True):
    from investigate_dsx01_localization_failures import fit
    from probe_ds23_frequency_events import summary
    from ds23_feasible_position import feasible_fit
    from probe_algo03_feasible_recovery import gate_slacks
    p,_=d['problems']['c0'];keep=d['keep'].copy()
    if restore:keep[p.slices[target]]=True
    pair={}
    for arm in ARMS:
        x=np.asarray(start,float).copy();reference=np.zeros(len(d['means']));history=[]
        if constrained_from:
            x=np.array(constrained_from[arm]['endpoint_east_north_km']);reference=np.array(constrained_from[arm]['phase_reference'])
        for _ in range(5):
            q=build(d,keep,arm,reference,target,sigma)
            if constrained_from:
                fitted=feasible_fit(lambda z:q.calculate(z)['negative_twice_elbo'],
                    lambda z:list(gate_slacks(q,z,d['entries']).values()),x,q.lower,q.upper,iterations=20)
            else:fitted=fit(q,x,iterations=48)
            x=np.asarray(fitted['parameters']);phase=np.clip(q.state(x)['phases'][q.labels],-15,15)
            history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
        r=summary(q,x,d['entries']);curved,pred,ids,_=report.memberships(q,x,d['entries'])
        r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
            curved_points=len(curved),predictive_points=len(pred),postfit_only_points=len(ids-curved-pred),
            proposed_associated_points=len(ids),proposed_associated_ids=sorted(ids))
        if constrained_from:r['minimum_gate_slack']=min(gate_slacks(q,x,d['entries']).values())
        pair[arm]=r
    return pair


def run(args):
    started=time.monotonic();out=args.output;out.mkdir(parents=True,exist_ok=False)
    d=load_case(args.root,args.case);baseline=baseline_pair(d)
    d,support,support_result=support_recovery(d,baseline)
    report.write(out/'support.json',support_result)
    candidates=offers(d,support);report.write(out/'offers.json',candidates)
    result=dict(case=args.case,baseline=baseline,support=support,policy=support,
        support_status=support_result['status'],status='no_eligible_removed_family')
    # Save the qualified fallback before any bounded expensive refinement.
    report.write(out/'fallback.json',result)
    if candidates:
        target=candidates[0];k=target['row'];result['proposal']=target;p,_=d['problems']['c0'];t=d['scan'].tracks[p.members[k]]
        screens={a:report.screen(q,x,t,np.arange(len(t['times'])),True) for a,(q,x) in d['problems'].items()}
        report.write(out/'catalogue.json',screens)
        agrees=all(r.get('norad')==target['norad'] and r['rms_hz']<=450 and abs(r['offset_hz'])<=3000
            and r['minimum_elevation_deg']>=0 for r in screens.values())
        if agrees:
            selected=select_width(d,k);report.write(out/'prior_selection.json',selected)
            result['selected_sigma_hz']=selected['selected_sigma_hz']
            pair=fit_pair(d,k,selected['selected_sigma_hz']);report.write(out/'unconstrained.json',pair)
            if not qualifies(pair,support):
                pair=fit_pair(d,k,selected['selected_sigma_hz'],constrained_from=pair);report.write(out/'constrained.json',pair)
            accepted=qualifies(pair,support)
            result.update(status='accepted' if accepted else 'rejected',proposal_pair=pair,
                          policy=pair if accepted else support)
        else:result['status']='catalogue_disagrees_or_physical_gate_fails'
    result['seconds']=time.monotonic()-started;report.write(out/'result.json',result)
    print(args.case,result['support_status'],result['status'],result.get('selected_sigma_hz'),result['seconds'],flush=True)


def freeze(args):
    args.output.mkdir(parents=True,exist_ok=False)
    old=report.read(args.parent/'protocol.json')
    report.write(args.output/'protocol.json',dict(root=str(args.root),primary_cases=old['selected'],
        remaining_cases=sorted(set(old['available'])-set(old['selected'])),
        proposal='largest wholly unassociated curved track >=20 points and >=24s whose original family has no retained curved/predictive evidence',
        identity='bounded whole causal catalogue screen in both arms must return original nominee',
        width_models_hz=[300,1000],width_selection='sum held predictive -2 log density over unique randomized 12s block partitions; wider requires gain >2 log(2) in each arm',
        split_seeds=[20261029,0,1],selection_position='preceding accepted RF endpoint held fixed; five nuisance phase refreshes',
        paired_c_controls=True,position_rounds=5,position_steps=48,constraint_steps=20,
        candidate_attempts_per_scan=1,job_cap_s=240,workers=4,
        observation_preservation=True,unchanged_residual_gates=True,
        inference_uses_GPS=False,post_scan_TLE=False,production_unchanged=True,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        sensitivity='conditional fixed-graph/identity/selected-width replay: starts +/-1km east/north and four 5Hz observation jitter seeds',
        note='Prospective algorithm protocol on previously analyzed same-site data, not a new-location validation'))


def sensitivity(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);d=load_case(args.root,args.case)
    baseline=baseline_pair(d);d,support,_=support_recovery(d,baseline)
    candidate=offers(d,support)[0];target=candidate['row'];start=np.array(args.start,float)
    if args.jitter_seed is not None:
        scan=copy.copy(d['scan']);scan.tracks=copy.deepcopy(scan.tracks)
        ids=sorted({oid for t in scan.tracks for oid in t['observation_ids']})
        rng=np.random.default_rng(args.jitter_seed);jitter=dict(zip(ids,rng.normal(0,5.,len(ids))))
        for t in scan.tracks:t['values']=np.asarray(t['values'])+np.array([jitter[oid] for oid in t['observation_ids']])
        d=dict(d,scan=scan)
    restore=args.mode!='sensitivity-control'
    pair=fit_pair(d,target,1000,start=start,restore=restore);report.write(out/'unconstrained.json',pair)
    if not qualifies(pair,support):
        pair=fit_pair(d,target,1000,constrained_from=pair,restore=restore);report.write(out/'constrained.json',pair)
    report.write(out/'sensitivity.json',dict(case=args.case,proposal=candidate,arms=pair,
        accepted=qualifies(pair,support),start_east_north_km=start,jitter_seed=args.jitter_seed,
        jitter_sigma_hz=5. if args.jitter_seed is not None else 0.,fixed_sigma_hz=1000,new_track_restored=restore,
        caveat='Conditional fixed graph, identity and prior; no GLRT reconstruction. Same ID gets same jitter in every occurrence.'))
    print(args.case,'sensitivity',start,args.jitter_seed,qualifies(pair,support),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','case','sensitivity','sensitivity-control'])
    p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--parent',type=Path);p.add_argument('--case');p.add_argument('--start',nargs=2,type=float,default=[0,0])
    p.add_argument('--jitter-seed',type=int);a=p.parse_args()
    freeze(a) if a.mode=='freeze' else sensitivity(a) if a.mode.startswith('sensitivity') else run(a)
