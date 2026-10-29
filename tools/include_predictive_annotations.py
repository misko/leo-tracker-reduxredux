"""Matched position trials without target-driven receiver calibration."""
import argparse
import copy
from pathlib import Path
import numpy as np
from annotate_predictive_only import context
from debug_fast_graph_unassociated import read,write,memberships
from leo.analysis.research.grouped_prediction import identity_consensus
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from annotate_track_predictively import corrected
from investigate_ds23_0268_remaining_tracks import family_frequency
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from investigate_dsx01_localization_failures import fit
from algo02_scan import pair_passes
from leo.analysis.research.retained_track_likelihood import profile


def annotation_noise_context(d):
    """Match the fixed noise policy used for identity validation, without mutation."""
    from annotate_track_predictively import training_factory
    scan=copy.copy(d['scan'])
    scan.fixed_window_noise=dict(scan.fixed_window_noise,extra_parameter_BIC_gain=0.)
    scan.radio_sigma_hz=150.
    return dict(d,scan=scan,powers=np.ones(len(d['powers'])),problem_factory=training_factory(dict(d)))


def target_orbit_context(d,families):
    """Add causal orbit uncertainty for target families using existing curved data."""
    from probe_ds23_history_calibrated_phase import make_problem
    original_factory=d.get('problem_factory',make_problem)
    def factory(*a,**k):
        original=original_factory(*a,**k)
        q=make_problem(*a,**k,support_policy=d.get('support_policy','nominal'),extra_orbital_families=families)
        q.constants[:]=original.constants
        q.point_noise=original.point_noise.copy()
        return q
    return dict(d,problem_factory=factory)


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);inv=read(args.inventory);d=context(inv);p0,x0=d['problems']['c0']
    noise_policy=getattr(args,'noise_policy','original')
    if noise_policy=='annotation_fixed':d=annotation_noise_context(d)
    original_graph_count=len(d['scan'].tracks);targets=[];receipts=[];used={o for e in d['entries'] for o in e['observation_ids']}
    used.update(o for i,sl in zip(p0.members,p0.slices,strict=True) for o,k in zip(d['scan'].tracks[i]['observation_ids'],d['keep'][sl],strict=True) if k)
    for folder in args.validation:
        r=read(folder/'result.json');annotation=identity_consensus(r['folds'],score_name=r['identity_score_name'])
        if annotation['status']!='conditionally_supported_identity':raise ValueError('annotation not conditionally supported')
        if args.native_branches:
            from native_predictive_branch import native_context
            d,t=native_context(d,inv,args.native_branches,r['track_id'])
        else:t=next(t for t in inv['tracks'] if t['track_id']==r['track_id'])
        i=t['track_index'];track=d['scan'].tracks[i]
        if i in p0.members:raise ValueError('this trial is for outside-calibration targets')
        if used.intersection(track['observation_ids']):raise ValueError('target duplicates calibration or predictive observations')
        used.update(track['observation_ids']);j=int(np.flatnonzero(d['scan'].norads==annotation['norad'])[0])
        if j not in p0.labels:raise ValueError('new-family phase-mixture inclusion requires its separate implementation')
        if args.native_branches:
            if not any(row['candidate_index']==j and d['keep'][sl].any() for row,sl in zip(p0.rows,p0.slices,strict=True)):
                raise ValueError('native branch needs an active shared family; use a new-family mixture otherwise')
            aliases={q['alias'] for f in r['folds'] for q in f['proposals'] if q['norad']==annotation['norad']}
            if len(aliases)!=1:raise ValueError('native branch alias unstable across partitions')
            alias=next(iter(aliases))
        else:
            f,_=family_frequency(p0,x0,j,times=track['times'])
            alias=int(profile_rate(corrected(p0,x0,i),track['rf_hz']/11.5e9*f,track['times'])['alias'][0])
        targets.append(dict(track_index=i,component=track['key'],candidate_index=j,norad=annotation['norad'],alias=alias,
            points=len(track['times']),observation_ids=track['observation_ids']))
        receipts.append(dict(path=str(folder),annotation=annotation))
    target_orbit_prior=getattr(args,'target_orbit_prior',False)
    shared_satellite_refresh=getattr(args,'shared_satellite_refresh',False)
    if target_orbit_prior:d=target_orbit_context(d,sorted({t['candidate_index'] for t in targets}))
    write(out/'protocol.json',dict(job=inv['job'],targets=targets,annotation_receipts=receipts,matched_c_arms=True,
        phase_rounds=5,steps=48,start=[0,0],box_width_km=25,target_calibrates_receiver=False,
        target_updates_unobserved_satellite_parameters=args.orphan_phase_refresh,
        original_noise_weights_and_priors=noise_policy=='original' and not target_orbit_prior,
        original_noise_weights=noise_policy=='original',noise_policy=noise_policy,orphan_phase_refresh=args.orphan_phase_refresh,
        orphan_orbit_prior=args.orphan_orbit_prior,GPS_used=False,future_TLE=False,
        target_orbit_prior=target_orbit_prior,
        shared_satellite_refresh=shared_satellite_refresh,
        native_branches=str(args.native_branches) if args.native_branches else None,original_graph_count=original_graph_count))
    variants=[('control',[])]+[(f'target_{k}',[t]) for k,t in enumerate(targets)]
    if len(targets)>1:variants.append(('combined',targets))
    for name,extras in variants:
        entries=d['entries']+extras;pair={}
        for arm in ['c0','fitted_c']:
            reference=np.zeros(len(d['means']));x=np.zeros(2);history=[]
            for _ in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                if args.orphan_orbit_prior:
                    from probe_ds23_history_calibrated_phase import make_problem
                    active={r['candidate_index'] for r,sl in zip(p0.rows,p0.slices,strict=True) if d['keep'][sl].any()}
                    families=sorted({e['candidate_index'] for e in targets}-active)
                    def factory(*a,**k):
                        original=d.get('problem_factory',make_problem)(*a,**k)
                        q=make_problem(*a,**k,support_policy=d.get('support_policy','nominal'),predictive_orbital_families=families)
                        q.constants[:]=original.constants
                        return q
                    kw={'base_problem_factory':factory}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,entries,d['powers'])
                if shared_satellite_refresh:
                    from shared_satellite_refresh import attach_shared_satellite_refresh
                    attach_shared_satellite_refresh(p,entries,d['powers'],[t['candidate_index'] for t in targets])
                if args.orphan_phase_refresh:
                    from predictive_orphan_phase import attach_orphan_phase
                    attach_orphan_phase(p,entries,d['powers'],orbital=args.orphan_orbit_prior)
                cached(p);fit_result=fit(p,x,iterations=48);x=np.asarray(fit_result['parameters'])
                phase=np.clip(p.state(x)['phases'][p.labels],-15,15);delta=float(np.max(abs(phase-reference)));reference=phase
                history.append(dict(endpoint_east_north_km=x,phase_change_s=delta))
            row=summary(p,x,entries)
            membership_view=copy.copy(p);membership_view.scan=copy.copy(p.scan);membership_view.scan.tracks=p.scan.tracks[:original_graph_count]
            _,_,ids,_=memberships(membership_view,x,entries);old=set(inv['policy'][arm]['proposed_associated_ids'])
            receiver_change=p.calculate(x).get('shared_satellite_receiver_change',row['linear_calibration_max_difference'])
            if receiver_change>1e-10:raise ValueError('predictive data changed receiver calibration at fixed position')
            row.update(history=history,final_phase_change_s=delta,proposed_associated_ids=sorted(ids),
                added_points=len(ids-old),lost_points=len(old-ids),targets=[g for g in row['linear_gates'] if g['component'] in {e['component'] for e in extras}])
            if args.native_branches and extras:
                calc=p.calculate(x);diagnostics=[]
                for entry,sl in zip(p.linear_entries,p.linear_slices,strict=True):
                    if entry not in extras:continue
                    track=p.scan.tracks[entry['track_index']];raw=calc['linear_raw_prediction_residual_hz'][sl]
                    terms=profile(raw,np.zeros(len(raw)),*p.scan.white[entry['track_index']],bias_sigma=300.)
                    diagnostics.append(dict(component=entry['component'],norad=entry['norad'],times_s=track['times'],CFO_hz=track['values'],
                        predicted_CFO_hz=track['values']-raw,residual_hz=terms['residual'][0],RMS_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0])))
                row['native_target_diagnostics']=diagnostics
            if args.orphan_phase_refresh:
                from predictive_orphan_phase import exact_phase_replay
                row['orphan_phase_replay']=exact_phase_replay(p,x,entries)
            if shared_satellite_refresh:
                from shared_satellite_refresh import exact_shared_replay
                row['shared_satellite_replay']=exact_shared_replay(p,x,entries)
            pair[arm]=row
        valid=pair_passes(pair,include_linear=True) and all(r['lost_points']==0 for r in pair.values())
        if args.orphan_phase_refresh:
            valid=valid and all(r['orphan_phase_replay']['phases_in_bounds'] and r['orphan_phase_replay']['maximum_phase_linearization_error_hz']<=1 for r in pair.values())
        if shared_satellite_refresh:
            valid=valid and all(r['shared_satellite_replay']['phases_in_bounds'] and r['shared_satellite_replay']['maximum_phase_linearization_error_hz']<=1 for r in pair.values())
        write(out/f'{name}.json',dict(job=inv['job'],arms=pair,baseline=inv['policy'],paired_valid=valid,
            target_entries=extras,original_calibration_mask=d['keep'],target_calibrates_receiver=False,
            target_updates_unobserved_satellite_parameters=args.orphan_phase_refresh,
            orphan_phase_refresh=args.orphan_phase_refresh,orphan_orbit_prior=args.orphan_orbit_prior,
            noise_policy=noise_policy,target_orbit_prior=target_orbit_prior,shared_satellite_refresh=shared_satellite_refresh,no_production_change=True))
        print(inv['job']['label'],name,valid,[(a,r['added_points'],r['lost_points']) for a,r in pair.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['inventory','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--validation',type=Path,nargs='+',required=True);p.add_argument('--orphan-phase-refresh',action='store_true')
    p.add_argument('--orphan-orbit-prior',action='store_true')
    p.add_argument('--noise-policy',choices=['original','annotation_fixed'],default='original')
    p.add_argument('--target-orbit-prior',action='store_true',help='Causal three-mode prior for active target families, using only original curved calibration')
    p.add_argument('--shared-satellite-refresh',action='store_true',help='Expose requested satellite predictive posterior means; preserve receiver means and all acceptance gates')
    p.add_argument('--native-branches',type=Path);a=p.parse_args()
    if a.orphan_orbit_prior and not a.orphan_phase_refresh:p.error('orbit prior requires phase refresh')
    if a.shared_satellite_refresh and a.orphan_phase_refresh:p.error('shared and orphan refresh are separate experiments')
    run(a)
