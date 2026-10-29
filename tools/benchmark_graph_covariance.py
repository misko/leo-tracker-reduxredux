"""Bounded DS24 comparison: nominal, active-support recovery, predictive covariance.

Inference never reads evaluation coordinates. Research endpoints must replay
before they can be used as controls. Independent processes own global scan paths.
"""

import argparse
import copy
from functools import partial
import hashlib
import itertools
from pathlib import Path
import time

import numpy as np

import debug_fast_graph_unassociated as report
from probe_high_channel_correlated_noise import calibrate, entries_for_targets, validation, position_trial

ARMS=('c0','fitted_c')


def load_case(root, case):
    import algo02_scan as algo
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from ds23_family_cavity import legacy_phase_reference
    from probe_ds23_frequency_events import cached
    algo.bind_run_directory(root)
    scan=algo.load_scan(root,case)
    saved=report.read(root/'family_cavity/position'/f'{case}.json')
    if saved['status']!='complete':raise ValueError('complete baseline required')
    chosen=saved['selected'] if saved['accepted'] else None
    node=copy.deepcopy(chosen['node'] if chosen else saved['baseline_node'])
    entries=copy.deepcopy(chosen['entries'] if chosen else saved['baseline_entries'])
    means=np.asarray(chosen['means'] if chosen else saved['baseline_means'])
    keep=np.asarray(saved['original_mask'],bool);powers=np.asarray(saved['powers']);model=saved['model']
    def build(arm,ref):
        p=make_event_problem(scan,node,keep,arm,np.asarray(ref),powers,means,model,[])
        attach_event_predictive(p,entries,powers)
        return p
    problems={};replay={}
    for arm in ARMS:
        row=saved['policy_arms'][arm];x=np.asarray(row['endpoint_east_north_km'])
        p=build(arm,row['phase_reference']);delta=p.calculate(x)['negative_twice_elbo']-row['negative_twice_elbo']
        if abs(delta)>1e-5:
            def posterior(ref,z):
                probe=build(arm,ref);return probe.state(z)['phases'][probe.labels]
            ref=legacy_phase_reference(row['history'],np.zeros(len(means)),posterior)
            p=build(arm,ref);delta=p.calculate(x)['negative_twice_elbo']-row['negative_twice_elbo']
        if abs(delta)>1e-5:raise ValueError(f'baseline replay mismatch {arm}: {delta}')
        problems[arm]=(cached(p),x);replay[arm]=float(delta)
    return dict(scan=scan,node=node,entries=entries,means=means,keep=keep,powers=powers,model=model,
                problems=problems,original={a:p for a,(p,x) in problems.items()},saved=saved,replay=replay,
                support_policy='nominal')


def compact_pair(pair):
    fields=('endpoint_east_north_km','endpoint_latlon','negative_twice_elbo','RMS_hz',
            'final_phase_change_s','curved_points','predictive_points','postfit_only_points',
            'proposed_associated_points','physical_target_checks','target_min_elevation_deg')
    return {a:{k:r[k] for k in fields if k in r} for a,r in pair.items()}


def baseline_pair(d):
    from probe_ds23_frequency_events import summary
    pair={}
    for a,(p,x) in d['problems'].items():
        r=summary(p,x,d['entries']);curved,pred,ids,_=report.memberships(p,x,d['entries'])
        r.update(curved_points=len(curved),predictive_points=len(pred),postfit_only_points=len(ids-curved-pred),
            proposed_associated_points=len(ids),proposed_associated_ids=sorted(ids),
            final_phase_change_s=d['saved']['policy_arms'][a].get('final_phase_change_s',0.))
        pair[a]=r
    return pair


def refit(d,keep,policy='active',entries=None,means=None):
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_history_calibrated_phase import make_problem
    from probe_ds23_frequency_events import cached,summary
    from investigate_dsx01_localization_failures import fit
    entries=d['entries'] if entries is None else entries; means=d['means'] if means is None else means
    pair={};problems={}
    for arm in ARMS:
        reference=np.zeros(len(means));x=np.zeros(2);history=[]
        for _ in range(5):
            p=make_event_problem(d['scan'],d['node'],keep,arm,reference,d['powers'],means,d['model'],[],
                base_problem_factory=partial(make_problem,support_policy=policy))
            attach_event_predictive(p,entries,d['powers']);cached(p)
            fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
            phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))))
            reference=phase
        r=summary(p,x,entries);curved,pred,ids,_=report.memberships(p,x,entries)
        r.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],
            curved_points=len(curved),predictive_points=len(pred),postfit_only_points=len(ids-curved-pred),
            proposed_associated_points=len(ids),proposed_associated_ids=sorted(ids))
        pair[arm]=r;problems[arm]=(p,x)
    return pair,problems


def support_recovery(d,baseline):
    from algo02_scan import pair_passes
    p,_=d['problems']['c0'];scan=d['scan'];owners={};offers=[]
    owned=set(baseline['c0']['proposed_associated_ids'])|set(baseline['fitted_c']['proposed_associated_ids'])
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        if p.keep[sl].any():owners.setdefault(row['candidate_index'],set()).add((scan.tracks[i]['receiver'],scan.tracks[i]['channel']))
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        t=scan.tracks[i];j=row['candidate_index']
        if (not p.keep[sl].any() and not owned.intersection(t['observation_ids']) and i in scan.curved
            and j in p.supported and len(owners.get(j,()))<2 and len(t['times'])>=12 and np.ptp(t['times'])>=10):
            offers.append((len(t['times']),float(np.ptp(t['times'])),k))
    if not offers:return d,baseline,dict(status='no_eligible_curve')
    _,_,k=max(offers);keep=d['keep'].copy();keep[p.slices[k]]=True
    pair,problems=refit(d,keep)
    accepted=pair_passes(pair,include_linear=True) and all(set(baseline[a]['proposed_associated_ids'])<=set(pair[a]['proposed_associated_ids']) for a in ARMS)
    result=dict(status='accepted' if accepted else 'rejected',component=p.rows[k]['component'],arms=pair)
    if not accepted:return d,baseline,result
    new=dict(d,keep=keep,problems=problems,support_policy='active')
    return new,pair,result


def nominate(d,pair,allow_single=False):
    p,x=d['problems']['c0'];scan=d['scan'];offers=[]
    owned=set(pair['c0']['proposed_associated_ids'])|set(pair['fitted_c']['proposed_associated_ids'])
    for k,(i,sl) in enumerate(zip(p.members,p.slices,strict=True)):
        t=scan.tracks[i]
        if t['channel'] not in (7,8) or len(t['times'])<20 or np.ptp(t['times'])<20 or owned.intersection(t['observation_ids']):continue
        r=report.screen(p,x,t,np.arange(len(t['times'])),False)
        if r['status']!='screened' or r['rms_hz']>450 or abs(r['offset_hz'])>3000 or r['minimum_elevation_deg']<0:continue
        offers.append(dict(row=k,receiver=t['receiver'],channel=t['channel'],norad=r['norad'],points=len(t['times']),screen=r))
    pairs=[]
    for left,right in itertools.combinations(offers,2):
        if left['receiver']!=right['receiver'] or left['channel']==right['channel'] or left['norad']!=right['norad']:continue
        times=[scan.tracks[p.members[r['row']]]['times'] for r in (left,right)]
        overlap=min(t.max() for t in times)-max(t.min() for t in times)
        if overlap<20:continue
        pairrows=sorted((left,right),key=lambda r:r['channel'])
        pairs.append(dict(rows=[r['row'] for r in pairrows],norad=left['norad'],
            receiver=left['receiver'],points=left['points']+right['points'],overlap_s=float(overlap)))
    pairs.sort(key=lambda r:(-r['points'],r['receiver'],r['norad'],r['rows']))
    if not pairs and allow_single:
        singles=[r for r in offers if np.ptp(r['screen']['times_s'])>=24]
        singles.sort(key=lambda r:(-r['points'],r['receiver'],r['norad'],r['row']))
        pairs=[dict(rows=[r['row']],norad=r['norad'],receiver=r['receiver'],points=r['points'],
                    overlap_s=0.,kind='single_curve_secondary') for r in singles]
    return dict(offers=offers,pairs=pairs,selected=pairs[0] if pairs else None)


def checks_pass(record):
    return record['noise']['noise_screen_pass'] and all(g['noise_screen_pass'] for g in record['per_track_noise'].values())


def position_pass(pair,old):
    return all(all(g['compatible'] for g in r['gates']['tracks']+r['linear_gates'])
        and checks_pass(r['target']) and r['target_min_elevation_deg']>=0 and r['final_phase_change_s']<=.01
        and all(abs(v['bias_hz'])<=3000 and v['raw_RMS_after_bias_hz']<=450 for v in r['physical_target_checks'])
        and set(old[a]['proposed_associated_ids'])<=set(r['proposed_associated_ids'])
        for a,r in pair.items())


def run_case(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);began=time.monotonic()
    d=load_case(args.root,args.case)
    if args.parent:
        previous=report.read(args.parent/'result.json');support_result=report.read(args.parent/'support.json')
        baseline=previous['baseline'];support=previous['support']
        if support_result['status']=='accepted':
            from ds23_frequency_events import make_event_problem,attach_event_predictive
            from probe_ds23_history_calibrated_phase import make_problem
            from probe_ds23_frequency_events import cached
            p,_=d['problems']['c0'];k=next(k for k,r in enumerate(p.rows) if r['component']==support_result['component'])
            keep=d['keep'].copy();keep[p.slices[k]]=True;problems={}
            for arm in ARMS:
                row=support[arm];x=np.asarray(row['endpoint_east_north_km'])
                q=make_event_problem(d['scan'],d['node'],keep,arm,np.asarray(row['phase_reference']),d['powers'],
                    d['means'],d['model'],[],base_problem_factory=partial(make_problem,support_policy='active'))
                attach_event_predictive(q,d['entries'],d['powers']);cached(q)
                if abs(q.calculate(x)['negative_twice_elbo']-row['negative_twice_elbo'])>1e-5:raise ValueError('support replay mismatch')
                problems[arm]=(q,x)
            d=dict(d,keep=keep,problems=problems,support_policy='active')
    else:
        baseline=baseline_pair(d);d,support,support_result=support_recovery(d,baseline)
    report.write(out/'support.json',support_result)
    nom=nominate(d,support,args.allow_single);report.write(out/'nomination.json',nom)
    outcome=dict(case=args.case,baseline=baseline,support=support,covariance=support,
        replay=d['replay'],total_GLRT=len(report.read(args.root/args.case/'observations.json')),
        support_status=support_result['status'],covariance_status='no_eligible_pair',
        support_policy=d['support_policy'])
    if nom['selected']:
        selected=nom['selected'];targets=selected['rows'];candidate=selected['norad']
        p,_=d['problems']['c0'];excluded=sorted({candidate,*[p.rows[k]['candidate_norad'] for k in targets]})
        calibration=calibrate(d,targets,excluded);report.write(out/'calibration.json',calibration)
        extras=entries_for_targets(d,targets,candidate);report.write(out/'entries.json',extras)
        model=calibration['best_correlated'];checks={};white_checks={}
        for seed in (20261029,0,1):
            checks[str(seed)]=validation(d,extras,model,seed)
            white_checks[str(seed)]=validation(d,extras,calibration['null'],seed)
        report.write(out/'validation.json',dict(correlated=checks,white=white_checks))
        passed=calibration['qualified'] and all(checks_pass(r['held']) and checks_pass(dict(r['joint'],per_track_noise={}))
            and r['held']['objective']<white_checks[seed][a]['held']['objective']
            for seed,check in checks.items() for a,r in check.items())
        # Challenge each incumbent family under exactly the same covariance.
        active=sorted({row['candidate_norad'] for row,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()})
        alternatives=[]
        for norad in sorted(set(active)|set(excluded)):
            if norad==candidate:continue
            alternative=validation(d,entries_for_targets(d,targets,norad),model)
            alternatives.append(dict(norad=norad,scores={a:r['joint']['objective'] for a,r in alternative.items()}))
        margins={a:min((r['scores'][a] for r in alternatives),default=float('inf'))-checks['20261029'][a]['joint']['objective'] for a in ARMS}
        report.write(out/'identity_challenge.json',dict(candidate=candidate,alternatives=alternatives,margins=margins))
        # Always propagate the fixed proposal as a labeled diagnostic, even
        # when its independent validation disqualifies policy adoption.
        proposed=position_trial(d,extras,model);report.write(out/'proposed_positions.json',proposed)
        accepted=passed and all(v>=10 for v in margins.values()) and position_pass(proposed,support)
        outcome.update(covariance_status='accepted' if accepted else 'rejected',
            covariance=proposed if accepted else support,provisional=proposed,
            covariance_validation_pass=bool(passed),identity_margins=margins,proposal=selected)
    outcome['seconds']=time.monotonic()-began
    report.write(out/'result.json',outcome)
    print(args.case,outcome['support_status'],outcome['covariance_status'],outcome['seconds'],flush=True)


def freeze(args):
    args.output.mkdir(parents=True,exist_ok=True)
    files=sorted((args.root/'family_cavity/position').glob('DS24-*.json'))
    available=[p.stem for p in files if report.read(p)['status']=='complete']
    selected=sorted(np.random.default_rng(2026102903).choice(available,12,replace=False).tolist())
    report.write(args.output/'protocol.json',dict(root=str(args.root),available=available,selected=selected,
        sample_seed=2026102903,selection='12 random completed fast DS24 cases; no error-based selection',
        source_record_sha256={p.stem:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        candidate='largest overlapping whole CH7/8 pair on one receiver, same incumbent-family nomination',
        minimum_points_per_curve=20,minimum_span_s=20,minimum_overlap_s=20,
        validation_seeds=[20261029,0,1],minimum_competing_identity_score_margin=10,
        covariance_grid='same predeclared independent-family grid as pilot; no target tuning',
        new_evidence_role='predictive only',future_TLE=False,position_truth_in_inference=False,
        initial_position_km=[0,0],search_box_width_km=25,phase_rounds=5,position_steps=48,
        production_unchanged=True,baseline='exact replay of saved production-equivalent signed/family baseline',
        note='Previously analyzed same-site recordings; new algorithm test, not new-site validation'))
    print(selected,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('freeze','case'));p.add_argument('--root',type=Path,required=True)
    p.add_argument('--case');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--allow-single',action='store_true');p.add_argument('--parent',type=Path)
    a=p.parse_args();freeze(a) if a.mode=='freeze' else run_case(a)
