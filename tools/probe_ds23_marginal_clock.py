"""Fixed-evidence clock quadrature, with proper UTC and an explicit profile control."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_delivery_clock_bounds import delivery_interval
from ds23_marginal_clock import uniform_quadrature,fixed_clock_node,attach_clock_prediction,MarginalClock
from investigate_dsx01_localization_failures import fit
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import cached,summary
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_marginal_clock'
COHORT=ROOT/'reports/2026_10_20_ds23_delivery_clock_position'
ARMS=('c0','fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in
        (Path(__file__),ROOT/'tools/ds23_marginal_clock.py',ROOT/'tools/ds23_delivery_clock_bounds.py')}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['source_sha256']!=hashes():raise ValueError('frozen clock quadrature experiment changed')
        return p
    original=read(COHORT/'protocol.json');development=original['development_cases']
    sizes=sorted((sum(read(SOURCE/c/'algo02_result.json')['mask']),c) for c in development)
    pilots=[sizes[k][1] for k in (0,len(sizes)//2,len(sizes)-1)]
    p=dict(development_cases=development,confirmation_cases=original['confirmation_cases'],
        pilot_cases=pilots,pilot_selection='minimum/median/maximum active curved point counts; no errors read',
        pilot_nodes=[7,15,31],pilot_arm='c0',pilot_positions='original regional center and saved RF incumbent; no GPS',
        quadrature_qualification=dict(maximum_objective_difference=.01,maximum_clock_mean_difference_s=.0001),
        source_sha256=hashes(),workers=24,methods=['correct_UTC_profile','correct_UTC_marginal'],
        hypothesis='integrate one uniform bounded common UTC offset; keep it distinct from orbital phase and propagate its uncertainty into linear predictive factors',
        geometry='UTC advances observation times, independent TLE phase alone undoes Earth rotation',
        earlier_UTC_prototypes_have_geometry_error=True,
        marginal_objective='normalized Gauss Legendre average of per-clock variational generalized RF evidence, including each conditional predictive factor',
        node_radio_and_reported_clock_posterior_from_curved_only=True,
        linear_factors_affect_marginal_position_objective_but_not_node_radio_calibration=True,
        integration_residual='responsibility-weighted component residuals plus exact discrete posterior KL',
        phase_reference='one independent phase-reference vector per quadrature node; five refresh rounds',
        phase_rounds=5,position_iterations=48,cold_start_km=[0,0],box_width_km=25,
        original_masks_labels_aliases_powers_noise_physical_priors_and_c_arm_matching=True,
        acceptance='original MAP-curved-clock node gates in both c arms, all-node phase convergence <=0.01; entire pair fallback otherwise',
        all_node_gate_mass_reported_not_used_for_GPS_selection=True,
        primary='fitted-c mean AND median improve in development and disjoint recording confirmation; all c0 results disclosed',
        quadrature_choice_before_geographic_evaluation=True,
        cohorts_reused_not_untouched_GPS_locations=True,no_GPS_future_TLE_new_RF_or_cross_scan_clock_fit=True)
    write(path,p);return p


def components(scan,node,keep,arm,powers,means,model,entries,shifts,references):
    result=[]
    for shift,reference in zip(shifts,references,strict=True):
        p=fixed_clock_node(scan,node,keep,arm,np.asarray(reference),powers,means,model,float(shift))
        attach_clock_prediction(p,entries,powers);cached(p);result.append(p)
    return result


def fixed_quadrature(scan,node,keep,arm,powers,means,model,entries,interval,count,position):
    shifts,weights=uniform_quadrature(interval['lower_s'],interval['upper_s'],count)
    reference=np.zeros((count,len(means)))
    for _ in range(5):
        nodes=components(scan,node,keep,arm,powers,means,model,entries,shifts,reference)
        next_reference=np.array([np.clip(p.state(position)['phases'][p.labels],-15,15) for p in nodes])
        change=float(np.max(abs(next_reference-reference)));reference=next_reference
    problem=MarginalClock(nodes,weights);c=problem.calculate(position)
    q=c['curved_clock_weights'];mean=float(q@shifts)
    return dict(negative_twice_RF_bound=c['negative_twice_elbo'],clock_mean_s=mean,
        clock_sigma_s=float(np.sqrt(q@((shifts-mean)**2))),node_phase_change_s=change,
        joint_clock_weights=c['joint_clock_weights'],curved_clock_weights=q,
        clock_nodes_s=shifts,quadrature_weights=weights,phase_reference_by_node=np.array([p.reference for p in nodes]))


def pilot(case):
    protocol=prepare();path=OUT/(case+'_pilot.json')
    if path.exists():return dict(case=case,cached=True)
    began=time.monotonic();scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    interval=delivery_interval(read(SOURCE/case/'tracking.json'),scan.receipt['origin_utc_ns'])
    positions=dict(center=np.zeros(2),incumbent=np.asarray(signed['policy_arms']['c0']['endpoint_east_north_km']))
    results={}
    for name,x in positions.items():
        results[name]={str(k):fixed_quadrature(scan,node,keep,'c0',powers,means,model,entries,interval,k,x)
                       for k in protocol['pilot_nodes']}
    write(path,dict(case=case,results=results,positions=positions,interval=interval,
        seconds=time.monotonic()-began,no_GPS_or_position_refit=True,source_sha256=hashes()))
    print(case,'quadrature pilot seconds',time.monotonic()-began,flush=True)
    return dict(case=case,seconds=time.monotonic()-began)


def qualify_quadrature():
    protocol=prepare();results={};rule=protocol['quadrature_qualification'];chosen=None
    for count in (7,15):
        comparisons=[]
        for case in protocol['pilot_cases']:
            r=read(OUT/(case+'_pilot.json'))
            for name,values in r['results'].items():
                a,b=values[str(count)],values['31']
                comparisons.append(dict(case=case,position=name,
                    objective_difference=abs(a['negative_twice_RF_bound']-b['negative_twice_RF_bound']),
                    clock_mean_difference_s=abs(a['clock_mean_s']-b['clock_mean_s']),
                    phase_changes=[a['node_phase_change_s'],b['node_phase_change_s']]))
        valid=all(r['objective_difference']<=rule['maximum_objective_difference'] and
                  r['clock_mean_difference_s']<=rule['maximum_clock_mean_difference_s'] and max(r['phase_changes'])<=.01
                  for r in comparisons)
        results[str(count)]=dict(qualified=valid,comparisons=comparisons)
        if valid and chosen is None:chosen=count
    record=dict(chosen_nodes=chosen,results=results,no_GPS_or_position_error_used=True,
        pilot_execution_sha256=sha(OUT/'pilot_execution.json'),source_sha256=hashes())
    write(OUT/'quadrature_selection.json',record);print('Quadrature chosen',chosen,results,flush=True)
    return record


def summarize_mixture(problem,position,entries,history,change):
    c=problem.calculate(position);mode=c['curved_clock_mode'];node=problem.nodes[mode]
    record=summary(node,position,entries)
    shifts=np.array([p.fixed_shift_s for p in problem.nodes]);q=c['curved_clock_weights'];mean=float(q@shifts)
    node_gates=[summary(p,position,entries) for p in problem.nodes]
    gate_pass=[all(r['compatible'] for r in d['gates']['tracks']+d['linear_gates']) for d in node_gates]
    record.update(history=history,final_phase_change_s=change,
        negative_twice_elbo=c['negative_twice_elbo'],MAP_node_negative_twice_elbo=record['negative_twice_elbo'],
        curved_mixture_objective=c['curved_mixture_objective'],curved_clock_weights=q,
        joint_clock_weights=c['joint_clock_weights'],clock_nodes_s=shifts,quadrature_weights=problem.weights,
        clock_posterior_mean_s=mean,clock_posterior_sigma_s=float(np.sqrt(q@((shifts-mean)**2))),
        curved_clock_mode=mode,MAP_common_UTC_shift_s=float(shifts[mode]),
        phase_reference_by_node=np.array([p.reference for p in problem.nodes]),
        node_gate_pass=gate_pass,curved_clock_gate_pass_mass=float(q@np.asarray(gate_pass)),
        clock_estimation_uncertainty_in_predictive_factors=True,
        node_calibration_is_curved_only=True)
    return record


def marginal_refit(scan,node,keep,arm,powers,means,model,entries,interval,count):
    shifts,weights=uniform_quadrature(interval['lower_s'],interval['upper_s'],count)
    references=np.zeros((count,len(means)));position=np.zeros(2);history=[]
    for epoch in range(5):
        nodes=components(scan,node,keep,arm,powers,means,model,entries,shifts,references)
        problem=MarginalClock(nodes,weights);cached(problem)
        fitted=fit(problem,position,iterations=48);position=np.asarray(fitted['parameters'])
        next_reference=np.array([np.clip(p.state(position)['phases'][p.labels],-15,15) for p in nodes])
        change=float(np.max(abs(next_reference-references)))
        history.append(dict(epoch=epoch,fit=fitted,all_node_phase_change_s=change));references=next_reference
    return summarize_mixture(problem,position,entries,history,change)


def profile_refit(scan,node,keep,arm,powers,means,model,entries,interval):
    def stage(fixed,linear):
        reference=np.zeros(len(means));x=np.zeros(3 if fixed is None else 2);history=[]
        for epoch in range(5):
            p=fixed_clock_node(scan,node,keep,arm,reference,powers,means,model,fixed,interval)
            attach_clock_prediction(p,linear,powers);cached(p)
            fitted=fit(p,x,iterations=48);x=np.asarray(fitted['parameters'])
            phase=np.clip(p.state(x)['phases'][p.labels],-15,15);change=float(np.max(abs(phase-reference)))
            history.append(dict(epoch=epoch,fit=fitted,phase_change_s=change));reference=phase
        record=summary(p,x,linear);record['endpoint_east_north_km']=x[:2]
        return dict(record,history=history,final_phase_change_s=change,common_UTC_shift_s=p.state(x)['common_UTC_shift_s'])
    curved=stage(None,[])
    shift=float(np.clip(curved['common_UTC_shift_s'],interval['lower_s'],interval['upper_s']))
    result=stage(shift,entries);result['curved_clock_estimate']=curved
    return result


def run(case,method):
    protocol=prepare();path=OUT/(case+'_'+method+'.json')
    if path.exists():return dict(case=case,method=method,cached=True)
    selection=read(OUT/'quadrature_selection.json');count=selection['chosen_nodes']
    if count is None:raise ValueError('clock quadrature not numerically qualified')
    began=time.monotonic();scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    interval=delivery_interval(read(SOURCE/case/'tracking.json'),scan.receipt['origin_utc_ns'])
    nulls=[]
    for arm in ARMS:
        old_arm=signed['policy_arms'][arm];x=np.asarray(old_arm['endpoint_east_north_km'])
        p=fixed_clock_node(scan,node,keep,arm,np.asarray(old_arm['phase_reference']),powers,means,model,0.)
        attach_clock_prediction(p,entries,powers)
        m=MarginalClock([p],[1.]);delta=m.calculate(x)['negative_twice_elbo']-old_arm['negative_twice_elbo']
        if abs(delta)>1e-3:raise ValueError('zero-width mixture does not reproduce the incumbent')
        nulls.append(dict(arm=arm,RF_difference=delta))
    pair={a:(marginal_refit(scan,node,keep,a,powers,means,model,entries,interval,count) if method=='marginal' else
             profile_refit(scan,node,keep,a,powers,means,model,entries,interval)) for a in ARMS}
    valid=pair_passes(pair,include_linear=True)
    write(path,dict(case=case,method=method,arms=pair,paired_valid=valid,accepted=valid,
        policy_arms=pair if valid else signed['policy_arms'],incumbent_arms=signed['policy_arms'],
        incumbent_binding=binding,null_endpoint_replays=nulls,interval=interval,original_mask=keep,
        seconds=time.monotonic()-began,GPS_used=False,future_TLE_used=False,source_sha256=hashes(),
        quadrature_selection_sha256=sha(OUT/'quadrature_selection.json')))
    print(case,method,'paired',valid,'seconds',time.monotonic()-began,flush=True)
    return dict(case=case,method=method,paired_valid=valid,seconds=time.monotonic()-began)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('pilot','qualify','development','confirmation'),required=True)
    args=parser.parse_args();protocol=prepare()
    if args.stage=='qualify':qualify_quadrature()
    else:
        tasks=[(c,) for c in protocol['pilot_cases']] if args.stage=='pilot' else [
            (c,m) for c in protocol[args.stage+'_cases'] for m in ('profile','marginal')]
        receipts=[]
        with ProcessPoolExecutor(max_workers=min(protocol['workers'],len(tasks))) as pool:
            futures={pool.submit(pilot if args.stage=='pilot' else run,*task):task for task in tasks}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(task=futures[f],error=repr(exc)))
                write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=len(tasks)))
        write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
        print('Terminal',len(receipts),'errors',sum('error'in r for r in receipts),flush=True)
