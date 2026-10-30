"""Bounded paired position trials of a pulse nominated without target values.

This is a selected-case research experiment, not an accepted production policy.
Event amplitude is marginalized jointly with existing calibration uncertainty;
event boundaries remain fixed hypotheses, requiring separate sensitivity tests.
"""
import argparse,hashlib,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem,attach_event_predictive,extend_event_associations,track_events
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from probe_ds23_frequency_events import cached,summary
from investigate_dsx01_localization_failures import fit
from phase_reference_checks import phase_refresh,reference_domain
from audit_explicit_phase_endpoint import exact_gate_replay
from audit_predictive_family_inclusion import owner_changes
from audit_ds23_algo01_coverage import retained_metrics
from investigate_ds23_0268_remaining_tracks import family_frequency
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from stress_joint_attachment import supervise
from leo.analysis.research.grouped_prediction import identity_consensus

METHODS=('null','receiver_hz','receiver_fractional','family_hz','family_fractional')


def event_memberships(p,x,entries):
    metrics=retained_metrics(p,x);extension=extend_event_associations(p,x,metrics)
    curved={oid for i,sl in zip(p.members,p.slices,strict=True) for oid,yes in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if yes}
    predictive={oid for e in entries for oid in e['observation_ids']};ids=curved|predictive;owners={}
    lookup={t['key']:t for t in p.scan.tracks}
    for row in extension['tracks']:
        if not row['compatible']:continue
        observation_ids=row.get('observation_ids',lookup[row['component']]['observation_ids'])
        if set(observation_ids)&predictive:continue
        ids.update(observation_ids);owners.update({oid:row['norad'] for oid in observation_ids})
    for e in entries:owners.update({oid:e['norad'] for oid in e['observation_ids']})
    return ids,owners


def target_prediction(p,x,target):
    c=p.calculate(x);view,values,*_=linear_geometry(p,[target]);g=geometry_features(view,x,0.)
    track=p.scan.tracks[target['track_index']];j=target['candidate_index']
    design=track_events(track,j,p.events);features=np.column_stack((g['features'],design))
    raw=values-view.q*g['intercept']-features@c['coefficient']
    begin=p.hardware.shape[1]+p.smooth.shape[1];end=begin+len(p.labels)+3*len(p.supported)
    exact,e=family_frequency(p,x,j,times=track['times'])
    approximate=view.q*g['intercept']+g['features'][:,begin:end]@c['coefficient'][begin:end]
    difference=view.q*exact-approximate;raw-=difference
    terms=profile(raw,np.zeros(len(raw)),*p.scan.white[target['track_index']],bias_sigma=300.)
    noise={k:v[0].item() for k,v in batch_noise_screen(terms['innovations'],track['times']).items()}
    return dict(component=track['key'],times_s=track['times'],CFO_hz=track['values'],
        residual_hz=terms['residual'][0],innovations_hz=terms['innovations'][0],RMS_hz=float(terms['rms'][0]),
        bias_hz=float(terms['bias'][0]),noise=noise,minimum_elevation_deg=float(e.min()),
        maximum_orbit_linearization_difference_hz=float(np.max(abs(difference))),
        constant_profiled_on_target=True,coefficient_prediction_excludes_target_calibration=True)


def one(args):
    inv=read(args.inventory);d=context(inv);trial=read(args.trial/'target_0.json');target=trial['target_entries'][0]
    base,_=d['problems']['c0'];sl=base.slices[base.members.index(target['track_index'])]
    if d['keep'][sl].any():raise ValueError('target must not calibrate receiver/event amplitude')
    targets=[target];extra_receipt=None
    if args.extra_validation:
        validation=read(args.extra_validation/'result.json');vote=identity_consensus(validation['folds'],score_name='conditional_target')
        if vote['status']!='conditionally_supported_identity':raise ValueError('extra identity unsupported')
        source=next(t for t in inv['tracks'] if t['track_id']==validation['track_id']);i=source['track_index']
        track=d['scan'].tracks[i];j=int(np.flatnonzero(d['scan'].norads==vote['norad'])[0])
        aliases={q['alias'] for f in validation['folds'] for q in f['proposals'] if q['norad']==vote['norad']}
        if len(aliases)!=1 or j!=target['candidate_index']:raise ValueError('same-family stable alias required')
        if d['keep'][base.slices[base.members.index(i)]].any():raise ValueError('extra target calibrates receiver')
        used={oid for e in d['entries']+targets for oid in e['observation_ids']}
        used.update(oid for k,ss in zip(base.members,base.slices,strict=True) for oid,active in zip(d['scan'].tracks[k]['observation_ids'],d['keep'][ss],strict=True) if active)
        if used.intersection(track['observation_ids']):raise ValueError('extra target duplicates observations')
        targets.append(dict(track_index=i,component=track['key'],candidate_index=j,norad=vote['norad'],alias=next(iter(aliases)),
            points=len(track['times']),observation_ids=track['observation_ids']))
        extra_receipt=dict(path=str(args.extra_validation),sha256=hashlib.sha256((args.extra_validation/'result.json').read_bytes()).hexdigest(),consensus=vote)
    nomination=read(args.nomination);chosen=next(r['pulse'] for r in nomination if r['arm']=='c0')
    # Scope/scaling change only; nomination uses the same saved c0 witnesses.
    event=dict(time_s=chosen['start_s']+args.start_shift,end_s=chosen['end_s']+args.end_shift,
        sigma_hz=chosen['amplitude_prior_sigma_hz'],rf_scaled=args.method.endswith('fractional'))
    if args.method.startswith('family'):event.update(kind='family',candidate_index=target['candidate_index'])
    else:event.update(kind='receiver',receiver=d['scan'].tracks[target['track_index']]['receiver'])
    events=[] if args.method=='null' else [event]
    args.output.mkdir(parents=True,exist_ok=False)
    write(args.output/'protocol.json',dict(job=inv['job'],method=args.method,events=events,target=target,targets=targets,extra_validation=extra_receipt,
        nomination=str(args.nomination),nomination_sha256=hashlib.sha256(args.nomination.read_bytes()).hexdigest(),
        boundary_nomination='prior c0 full-data target-excluded witness diagnostic; selected case',
        boundary_shifts_s=[args.start_shift,args.end_shift],target_calibrates_event=False,
        event_boundary_uncertainty_integrated=False,event_amplitude_uncertainty_integrated=True,
        original_noise_weights_priors=True,matched_c=True,GPS_used=False,future_TLE=False,
        phase_rounds=5,iterations=48,regional_start=[0,0],box_width_km=25,no_production_change=True))
    old={};oldids={};controls={};records=[]
    for arm,(p,x) in d['problems'].items():
        _,_,ids,owners=memberships(p,x,d['entries'])
        if ids!=set(inv['policy'][arm]['proposed_associated_ids']):raise ValueError('incumbent membership replay failed')
        old[arm]=owners;oldids[arm]=ids
    for role in ('control','addition'):
        entries=d['entries']+(targets if role=='addition' else []);pair={}
        for arm in ('c0','fitted_c'):
            kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
            x=np.zeros(2);reference=np.zeros(len(d['means']));history=[]
            for _ in range(5):
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],events,**kw)
                attach_event_predictive(p,entries,d['powers']);cached(p)
                fr=fit(p,x,iterations=48);x=np.asarray(fr['parameters'])
                reference,check=phase_refresh(p.state(x)['phases'][p.labels],reference)
                history.append(dict(endpoint_east_north_km=x,**check))
            c=p.calculate(x);row=summary(p,x,entries);ids,owners=event_memberships(p,x,entries)
            if role=='control':controls[arm]=owners
            labels={r['candidate_index'] for r,ss in zip(p.rows,p.slices,strict=True) if p.keep[ss].any()}
            labels.update(e['candidate_index'] for e in entries);exact=[]
            for j in sorted(labels):
                p.explicit_phase_family=j
                exact.append(dict(norad=int(p.scan.norads[j]),**exact_gate_replay(p,x,entries)))
            phase=p.state(x)['phases'];domain=reference_domain(p.sky['time_s'],p.flat_times,p.flat_labels,phase[p.labels],padding_s=0)
            if entries:
                view,*_=linear_geometry(p,entries)
                domain['predictive']=reference_domain(p.sky['time_s'],view.flat_times,view.flat_labels,phase[p.labels],padding_s=0)
            changed=owner_changes(old[arm],owners);control_changed=owner_changes(controls[arm],owners)
            row.update(history=history,final_phase_change_s=check['phase_change_s'],domains=domain,
                proposed_associated_ids=sorted(ids),proposed_owners=owners,added_points=len(ids-oldids[arm]),lost_points=len(oldids[arm]-ids),
                incumbent_owner_changes=changed,control_owner_changes=control_changed,exact_replays=exact,
                exact_target=target_prediction(p,x,target),role=role,arm=arm,method=args.method,
                extra_target_predictions=[target_prediction(p,x,t) for t in targets[1:]],
                evidence_qualified=bool(not changed and not control_changed and all(r['all_pass'] for r in exact)
                    and check['phase_change_s']<=.01 and domain['in_domain'] and domain.get('predictive',{'in_domain':True})['in_domain']))
            # Null event amplitude must reproduce the no-event posterior at
            # exactly the same position/reference, apart from its unused slot.
            if args.method=='null':
                zero=make_event_problem(d['scan'],d['node'],d['keep'],arm,p.reference,d['powers'],d['means'],d['model'],[dict(event,sigma_hz=0.)],**kw)
                attach_event_predictive(zero,entries,d['powers']);z=zero.calculate(x)
                delta=float(z['negative_twice_elbo']-c['negative_twice_elbo'])
                maxres=float(np.max(abs(z['conditional_residual_hz']-c['conditional_residual_hz'])))
                if abs(delta)>1e-5 or maxres>1e-5:raise ValueError('zero event changes baseline objective/residual')
                row['zero_event_equivalence']=dict(objective_difference=delta,maximum_residual_difference_hz=maxres)
                normal_ids,normal_owners=event_memberships(p,x,entries)
                _,_,reference_ids,reference_owners=memberships(p,x,entries)
                if normal_ids!=reference_ids or normal_owners!=reference_owners:raise ValueError('no-event membership differs')
            pair[arm]=row;records.append(row)
            print(args.method,role,arm,'qualified',row['evidence_qualified'],'target RMS',round(row['exact_target']['RMS_hz'],2),flush=True)
        write(args.output/(role+'.json'),dict(job=inv['job'],method=args.method,events=events,target=target,arms=pair,
            paired_valid=all(v['evidence_qualified'] for v in pair.values()),no_accepted_policy_change=True))
    write(args.output/'result.json',dict(job=inv['job'],method=args.method,events=events,rows=records,
        experimental_target_inclusion=all(r['evidence_qualified'] for r in records),no_accepted_policy_change=True))


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    jobs=[dict(method=m,start_shift=0.,end_shift=0.,name=m) for m in METHODS]
    if args.boundary_sensitivity:
        jobs=[dict(method=m,start_shift=a,end_shift=b,name=f'{m}-start{a:+.1f}-end{b:+.1f}')
              for m in ('receiver_hz','family_hz') for a in (-.5,.5) for b in (-.5,.5)]
    if not 1<=args.workers<=4:raise ValueError('one to four workers required')
    write(args.output/'protocol.json',dict(jobs=jobs,inventory=str(args.inventory),trial=str(args.trial),nomination=str(args.nomination),
        workers=args.workers,seconds_per_job=300,boundary_sensitivity=args.boundary_sensitivity,
        selection='All +/-0.5 s boundary corners for both additive-Hz scopes' if args.boundary_sensitivity else 'All four event scope/scaling combinations plus no-event control; no GPS ranking',
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.inventory,args.trial/'target_0.json',args.nomination)}))
    def work(j):
        cmd=[sys.executable,__file__,'one','--inventory',str(args.inventory),'--trial',str(args.trial),'--nomination',str(args.nomination),
            '--method',j['method'],'--start-shift',str(j['start_shift']),'--end-shift',str(j['end_shift']),'--output',str(args.output/j['name'])]
        if args.extra_validation:cmd.extend(['--extra-validation',str(args.extra_validation)])
        terminal=dict(**j,command=cmd,**supervise(cmd,args.output/(j['name']+'.log'),300))
        write(args.output/(j['name']+'-terminal.json'),terminal);return terminal
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(work,j) for j in jobs]):print(f.result(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['run','one'])
    for name in ('inventory','trial','nomination','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--method',choices=METHODS);p.add_argument('--start-shift',type=float,default=0.);p.add_argument('--end-shift',type=float,default=0.)
    p.add_argument('--boundary-sensitivity',action='store_true');p.add_argument('--workers',type=int,default=2)
    p.add_argument('--extra-validation',type=Path)
    a=p.parse_args();run(a) if a.mode=='run' else one(a)
