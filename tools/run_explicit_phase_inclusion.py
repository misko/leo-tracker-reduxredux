"""Bounded matched RF-only position/phase continuation with unchanged gates."""
import argparse,copy
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write,memberships
from diagnose_all_large_tracks import context
from native_predictive_branch import native_context,validated_native_source
from leo.analysis.research.grouped_prediction import identity_consensus
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached,summary
from ds23_feasible_position import feasible_fit
from probe_algo03_feasible_recovery import gate_slacks
from explicit_shared_phase import attach_explicit_phase,PHASE_UNIT_S,evidence_context
from shared_satellite_refresh import exact_shared_replay
from algo02_scan import pair_passes
from leo.analysis.research.retained_track_likelihood import profile


def run(args):
    out=args.output;out.mkdir(exist_ok=False,parents=True);pr=read(args.diagnostic/'protocol.json')
    inv=read(Path(pr['inventory']));d=context(inv);graph_count=len(d['scan'].tracks)
    noise_policy=getattr(args,'noise_policy','original')
    d=evidence_context(d,noise_policy)
    validation=Path(pr['validation']);annotation=read(validation/'result.json')
    vote=identity_consensus(annotation['folds'],score_name=annotation['identity_score_name'])
    if vote['status']!='conditionally_supported_identity':raise ValueError('unsupported native identity')
    source=validated_native_source(validation);target=pr['target'];j=target['candidate_index']
    if target['norad']!=vote['norad']:raise ValueError('identity mismatch')
    d,_=native_context(d,inv,source,annotation['track_id'])
    p0,_=d['problems']['c0'];used={o for e in d['entries'] for o in e['observation_ids']}
    used.update(o for i,sl in zip(p0.members,p0.slices,strict=True) for o,k in zip(d['scan'].tracks[i]['observation_ids'],d['keep'][sl],strict=True) if k)
    if used.intersection(target['observation_ids']):raise ValueError('native duplicates original model points')
    write(out/'protocol.json',dict(source_diagnostic=str(args.diagnostic),source_protocol=pr,job=inv['job'],
        target=target,constrained=args.constrained,matched_c=True,original_noise_and_priors=noise_policy=='original',
        noise_policy=noise_policy,original_prior_widths=True,original_noise_weights=noise_policy=='original',
        fixed_noise_hz=150 if noise_policy in ('annotation_fixed','fixed_noise_only') else None,
        original_curve_powers=noise_policy in ('original','fixed_noise_only'),
        GPS_used=False,future_TLE=False,target_updates_receiver_at_fixed_position=False,
        fixed_coordinates_conditioned_not_marginalized=True,phase_density_normalizer_included=True,
        phase_rounds=5,steps_per_round=48,phase_start_grid='81 phases within +/-0.2s of incumbent, clipped to +/-15s',
        start='accepted RF incumbent in original 25x25km regional box',phase_optimizer_unit_seconds=PHASE_UNIT_S,
        objective='curved ELBO plus conditional phase density plus predictive density with constants integrated',
        original_model_comparison_requires_matched_control=True,no_production_change=True))
    for role,extras in [('control',[]),('target',[target])]:
        entries=d['entries']+extras;arms={}
        for arm in ('c0','fitted_c'):
            incumbent=inv['policy'][arm];x=np.array(incumbent['endpoint_east_north_km']);reference=np.array(incumbent['phase_reference'])
            z=None;history=[]
            for epoch in range(5):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,entries,d['powers'])
                initial_phase=float(p.state(x)['phases'][j]) if z is None else z[2]*PHASE_UNIT_S
                attach_explicit_phase(p,entries,d['powers'],j);cached(p)
                if z is None:
                    initial=[]
                    for phi in np.unique(np.clip(initial_phase+np.linspace(-.2,.2,81),-15,15)):
                        candidate=np.r_[x,phi/PHASE_UNIT_S];score=p.calculate(candidate)['negative_twice_elbo']
                        slack=min(gate_slacks(p,candidate,entries).values())
                        initial.append(dict(parameters=candidate,score=score,minimum_gate_slack=slack))
                    feasible=[v for v in initial if v['minimum_gate_slack']>=0]
                    pick=min(feasible,key=lambda v:v['score']) if args.constrained and feasible else min(initial,key=lambda v:v['score'])
                    z=np.array(pick['parameters']);write(out/f'{role}-{arm}-initial.json',dict(candidates=initial,selected=pick))
                constraints=(lambda q:list(gate_slacks(p,q,entries).values())) if args.constrained else (lambda q:[1.])
                fit=feasible_fit(lambda q:p.calculate(q)['negative_twice_elbo'],constraints,z,p.lower,p.upper,iterations=48)
                z=np.asarray(fit['parameters']);x=z[:2];phase=np.clip(p.state(z)['phases'][p.labels],-15,15)
                change=float(np.max(abs(phase-reference)));reference=phase
                history.append(dict(fit=fit,phase_change_s=change,exact_phase=exact_shared_replay(p,z,entries)))
            row=summary(p,z,entries);calc=p.calculate(z)
            row.update(endpoint_east_north_km=z[:2],optimizer_parameters=z,history=history,final_phase_change_s=change,
                objective_kind=calc['objective_kind'],explicit_phase_density=calc['explicit_phase_density'],
                phase_conditional_precision=calc['explicit_phase_conditional_precision'],
                exact_phase=exact_shared_replay(p,z,entries),all_gate_slacks=gate_slacks(p,z,entries),
                receiver_coefficient_change=calc['shared_satellite_receiver_change'])
            view=copy.copy(p);view.scan=copy.copy(p.scan);view.scan.tracks=p.scan.tracks[:graph_count]
            _,_,ids,owners=memberships(view,z,entries);old=set(incumbent['proposed_associated_ids'])
            row.update(proposed_associated_ids=sorted(ids),proposed_owners=owners,added_points=len(ids-old),lost_points=len(old-ids))
            if row['receiver_coefficient_change']!=0:raise ValueError('receiver changed at fixed position')
            diagnostics=[]
            for entry,sl in zip(entries,p.linear_slices,strict=True):
                if entry not in extras:continue
                t=p.scan.tracks[entry['track_index']];raw=calc['linear_raw_prediction_residual_hz'][sl]
                terms=profile(raw,np.zeros(len(raw)),*p.scan.white[entry['track_index']],bias_sigma=300.)
                diagnostics.append(dict(component=entry['component'],times_s=t['times'],CFO_hz=t['values'],
                    predicted_CFO_hz=t['values']-raw,residual_hz=terms['residual'][0],RMS_hz=float(terms['rms'][0])))
            row['native_target_diagnostics']=diagnostics;arms[arm]=row
            write(out/f'{role}-{arm}.json',row)
            print(role,arm,'end',z,'min slack',min(row['all_gate_slacks'].values()),'added/lost',row['added_points'],row['lost_points'],flush=True)
        valid=pair_passes(arms,include_linear=True) and all(v['lost_points']==0 and v['exact_phase']['phases_in_bounds'] and
            v['exact_phase']['maximum_phase_linearization_error_hz']<=1 for v in arms.values())
        write(out/f'{role}.json',dict(job=inv['job'],arms=arms,paired_valid=valid,baseline=inv['policy'],
            target_entries=extras,constrained=args.constrained,explicit_phase=True,noise_policy=noise_policy,no_production_change=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--diagnostic',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--constrained',action='store_true')
    p.add_argument('--noise-policy',choices=['original','annotation_fixed','fixed_noise_only','unit_weights_only'],default='original');run(p.parse_args())
