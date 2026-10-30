"""Replay held-block endpoints without optimizing or consulting held values."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from native_predictive_branch import native_context,validated_native_source
from grouped_predictive_scan import predictive_training_views
from annotate_track_predictively import training_factory,prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from explicit_shared_phase import attach_explicit_phase
from probe_ds23_frequency_events import cached
from validate_explicit_phase_position import held_predictions
from leo.analysis.research.grouped_prediction import replay_split
from phase_reference_checks import phase_refresh


def run(args):
    rows=[];executions=[]
    for job in read(args.batch/'protocol.json')['jobs']:
        root=args.batch/job['name'];term=read(args.batch/(job['name']+'-terminal.json'))
        executions.append(dict(name=job['name'],status=term['status']))
        if term['status']!='complete':continue
        saved=read(root/'result.json');protocol=read(root/'protocol.json');pr=protocol['source_protocol']
        inv=read(Path(pr['inventory']));d=context(inv);target=pr['target']
        d,_=native_context(d,inv,validated_native_source(Path(pr['validation'])),target['component'].split('-NATIVE-')[-1])
        split=saved['split'];p0,_=d['problems']['c0'];train,held=replay_split(p0.flat_times,split)
        keep=d['keep']&train;held_old=d['keep']&held
        for sl in p0.slices:
            if 0<keep[sl].sum()<4:keep[sl]=False
        scan,all_entries,_=predictive_training_views(d['scan'],d['entries']+[target],split)
        native=next(e for e in all_entries if e['component']==target['component']+'-TRAIN')
        entries=[e for e in all_entries if e is not native];unit=np.ones(len(d['powers']))
        weights=root/'curve_weights.json';powers=np.asarray(read(weights)['powers']) if weights.exists() else unit
        training=dict(d,scan=scan,entries=entries,powers=powers);factory=training_factory(training)
        for arm,a in saved['arms'].items():
            means,_=prior_means(training,d['node']);ref=np.zeros(len(means))
            for step in a['start_training']['history']:
                p=make_event_problem(scan,d['node'],keep,arm,ref,unit,means,d['model'],[],base_problem_factory=factory)
                x=np.array(step['endpoint']);ref=np.clip(p.state(x)['phases'][p.labels],-15,15)
            initial_ref=p.reference.copy()
            start_delta=p.calculate(x)['negative_twice_elbo']-a['start_training']['training_objective']
            if abs(start_delta)>1e-5:raise ValueError('training start replay failed')
            for role,v in a['variants'].items():
                selected=entries+([native] if role=='target' else []);ref=initial_ref.copy()
                for step in v['history']:
                    p=make_event_problem(scan,d['node'],keep,arm,ref,powers,d['means'],d['model'],[],base_problem_factory=factory)
                    attach_event_predictive(p,selected,powers);attach_explicit_phase(p,selected,powers,target['candidate_index']);cached(p)
                    z=np.array(step['fit']['parameters']);ref=np.clip(p.state(z)['phases'][p.labels],-15,15)
                delta=p.calculate(z)['negative_twice_elbo']-v['training_objective']
                predicted=held_predictions(p,z,d,target,split,held_old)
                if [r['component'] for r in predicted]!=[r['component'] for r in v['held_predictions']]:raise ValueError('held rows changed')
                difference=max(float(np.max(abs(np.array(a['residual_hz'])-b['residual_hz']))) for a,b in zip(predicted,v['held_predictions'],strict=True))
                if abs(delta)>1e-5 or difference>1e-5:raise ValueError('held endpoint replay failed')
                # Probe the fitted objective's independence from excluded curved
                # observations, holding the graph and all prior choices fixed.
                q=make_event_problem(scan,d['node'],keep,arm,p.reference.copy(),powers,d['means'],d['model'],[],base_problem_factory=factory)
                q.values=q.values.copy();q.values[~keep]+=1e6
                attach_event_predictive(q,selected,powers);attach_explicit_phase(q,selected,powers,target['candidate_index']);cached(q)
                poison_delta=q.calculate(z)['negative_twice_elbo']-p.calculate(z)['negative_twice_elbo']
                if abs(poison_delta)>1e-5:raise ValueError('excluded values influence fitted objective')
                _,check=phase_refresh(p.state(z)['phases'][p.labels],p.reference)
                rows.append(dict(scan=job['scan'],seed=job['seed'],arm=arm,role=role,
                    start_objective_difference=start_delta,objective_difference=delta,maximum_held_residual_difference_hz=difference,
                    excluded_curved_values_perturbation_hz=1e6,perturbed_objective_difference=poison_delta,
                    phase_reference=p.reference,phase_state=p.state(z)['phases'],
                    phase_reference_check=check,raw_training_qualified=bool(v['training_gates']['all_pass'] and check['phase_change_s']<=.01),
                    conditional_on_frozen_graph_identities_and_priors=True))
        print(job['name'],'replayed',flush=True)
    write(args.output,dict(rows=rows,executions=executions,no_optimization=True,no_acceptance_changes=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
