"""Randomized training-only position/phase fitting with held-family prediction.

Frozen graph, identity and pre-existing prior choices remain conditioning
assumptions. This is not independent identity validation or a global rerun.
"""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from native_predictive_branch import native_context,validated_native_source
from annotate_track_predictively import fit_training,training_factory
from grouped_predictive_scan import predictive_training_views
from ds23_frequency_events import make_event_problem,attach_event_predictive
from explicit_shared_phase import attach_explicit_phase,PHASE_UNIT_S
from probe_ds23_frequency_events import cached
from ds23_feasible_position import feasible_fit
from probe_algo03_feasible_recovery import gate_slacks
from audit_explicit_phase_endpoint import exact_gate_replay
from investigate_ds23_0268_remaining_tracks import family_frequency
from probe_shared_phase_feasibility import fixed_alias_constant
from leo.analysis.research.grouped_prediction import replay_split
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features


def held_predictions(p,z,d,target,split,held_old):
    c=p.calculate(z);frequency,_=p.conditional_frequency(z);rows=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        held=held_old[sl]
        if not held.any():continue
        t=p.scan.tracks[i];f,_=family_frequency(p,z,row['candidate_index'],times=t['times'])
        residual=c['conditional_residual_hz'][sl]-p.q[sl]*(f-frequency[sl])
        rows.append(dict(component=t['key'],kind='curved',norad=row['candidate_norad'],candidate_index=row['candidate_index'],
            same_family=row['candidate_index']==target['candidate_index'],receiver=t['receiver'],channel=t['channel'],
            train_points=int(p.keep[sl].sum()),held_points=int(held.sum()),times_s=t['times'][held],
            observation_ids=np.asarray(t['observation_ids'])[held],residual_hz=residual[held],RMS_hz=float(np.sqrt(np.mean(residual[held]**2)))))
    for entry in d['entries']+[target]:
        t=p.scan.tracks[entry['track_index']];train,held=replay_split(t['times'],split)
        if not held.any():continue
        view,values,*_=linear_geometry(p,[entry]);geometry=geometry_features(view,z,0.)
        begin=p.hardware.shape[1]+p.smooth.shape[1];f,_=family_frequency(p,z,entry['candidate_index'],times=t['times'])
        raw=values-geometry['features'][:,:begin]@c['coefficient'][:begin]-view.q*f
        bias=fixed_alias_constant(raw[train],np.full(int(train.sum()),1/(2*150**2)),1/300**2)['bias_hz'] if train.any() else 0.
        residual=raw[held]-bias
        rows.append(dict(component=t['key'],kind='native' if entry is target else 'predictive',norad=entry['norad'],candidate_index=entry['candidate_index'],
            same_family=entry['candidate_index']==target['candidate_index'],receiver=t['receiver'],channel=t['channel'],
            train_points=int(train.sum()),held_points=int(held.sum()),times_s=t['times'][held],
            observation_ids=np.asarray(t['observation_ids'])[held],residual_hz=residual,RMS_hz=float(np.sqrt(np.mean(residual**2))),training_bias_hz=bias))
    return rows


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);pr=read(args.diagnostic/'protocol.json')
    inv=read(Path(pr['inventory']));d=context(inv);source=validated_native_source(Path(pr['validation']));target=pr['target']
    d,_=native_context(d,inv,source,target['component'].split('-NATIVE-')[-1])
    annotation=read(Path(pr['validation'])/'result.json');fold=next(f for f in annotation['folds'] if f['seed']==args.seed);split=fold['split']
    p0,_=d['problems']['c0'];train,held=replay_split(p0.flat_times,split);keep=d['keep']&train
    excluded=[]
    for i,sl in zip(p0.members,p0.slices,strict=True):
        if 0<keep[sl].sum()<4:excluded.append(dict(component=d['scan'].tracks[i]['key'],points=int(keep[sl].sum())));keep[sl]=False
    held_old=d['keep']&held
    scan,training_entries,receipts=predictive_training_views(d['scan'],d['entries']+[target],split)
    native=next((e for e in training_entries if e['component']==target['component']+'-TRAIN'),None)
    if native is None or native['points']<8:raise ValueError('insufficient native training points')
    entries=[e for e in training_entries if e is not native]
    calibration_ids={oid for i,sl in zip(p0.members,p0.slices,strict=True) for oid,use in zip(d['scan'].tracks[i]['observation_ids'],keep[sl],strict=True) if use}
    predictive_ids=[oid for e in training_entries for oid in e['observation_ids']]
    if len(predictive_ids)!=len(set(predictive_ids)) or calibration_ids&set(predictive_ids):raise ValueError('training observations double counted')
    training=dict(d,scan=scan,entries=entries,powers=np.ones(len(d['powers'])))
    factory=training_factory(training);powers=np.ones(len(d['powers']));arms={}
    write(out/'protocol.json',dict(source_protocol=pr,job=inv['job'],seed=args.seed,split=split,matched_c=True,
        GPS_used=False,future_TLE=False,scanwide_held_blocks_excluded_from_all_fits=True,
        original_graph_identities_and_prior_choices_fixed=True,independent_identity_validation=False,
        fixed_training_noise_hz=150,training_curve_powers='all one',predictive_variance_multiplier=2,
        training_entry_receipts=receipts,excluded_small_curved_training_groups=excluded,
        held_values_never_fit_constants=True,phase_rounds=5,iterations=48,phase_start_grid_points=81,
        start='training-only curved fit from regional center; same start for control and native',
        evaluation='exact mean residuals at plug-in position/phase; no predictive uncertainty integration',
        no_accepted_associations=True))
    for arm in ('c0','fitted_c'):
        base,x,meta=fit_training(training,d['node'],keep,arm);start_reference=base.reference.copy()
        initial_phase=float(base.state(x)['phases'][target['candidate_index']]);results={}
        for role,extra in [('control',[]),('target',[native])]:
            selected=entries+extra;z=np.r_[x,initial_phase/PHASE_UNIT_S];reference=start_reference.copy();history=[]
            for epoch in range(5):
                p=make_event_problem(scan,d['node'],keep,arm,reference,powers,d['means'],d['model'],[],base_problem_factory=factory)
                attach_event_predictive(p,selected,powers);attach_explicit_phase(p,selected,powers,target['candidate_index']);cached(p)
                if epoch==0:
                    grid=[]
                    for phi in np.unique(np.clip(initial_phase+np.linspace(-.2,.2,81),-15,15)):
                        q=np.r_[x,phi/PHASE_UNIT_S];grid.append(dict(parameters=q,score=p.calculate(q)['negative_twice_elbo'],minimum_slack=min(gate_slacks(p,q,selected).values())))
                    feasible=[q for q in grid if q['minimum_slack']>=0]
                    pick=min(feasible,key=lambda q:q['score']) if feasible else min(grid,key=lambda q:q['score'])
                    z=np.asarray(pick['parameters']);write(out/f'{arm}-{role}-initial.json',dict(candidates=grid,selected=pick))
                fitted=feasible_fit(lambda q:p.calculate(q)['negative_twice_elbo'],lambda q:list(gate_slacks(p,q,selected).values()),z,p.lower,p.upper,iterations=48)
                z=np.asarray(fitted['parameters']);phase=np.clip(p.state(z)['phases'][p.labels],-15,15)
                change=float(np.max(abs(phase-reference)));reference=phase;history.append(dict(fit=fitted,phase_change_s=change))
            audit=exact_gate_replay(p,z,selected);c=p.calculate(z)
            results[role]=dict(endpoint_east_north_km=z[:2],optimizer_parameters=z,history=history,
                phase_reference=p.reference.copy(),phase_state=p.state(z)['phases'],
                final_phase_change_s=change,training_objective=c['negative_twice_elbo'],
                training_gates=audit,training_qualified=bool(audit['all_pass'] and change<=.01),
                receiver_change=c['shared_satellite_receiver_change'],held_predictions=held_predictions(p,z,d,target,split,held_old))
            write(out/f'{arm}-{role}.json',results[role])
            print(inv['job']['label'],args.seed,arm,role,'qualified',results[role]['training_qualified'],'endpoint',z[:2],flush=True)
        arms[arm]=dict(start_training=meta,variants=results)
    write(out/'result.json',dict(job=inv['job'],seed=args.seed,split=split,target=target,arms=arms,conditional_model_validation=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--diagnostic',type=Path,required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
