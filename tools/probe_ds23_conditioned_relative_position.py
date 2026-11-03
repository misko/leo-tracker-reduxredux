"""Restore hierarchical priors and test conditionally nominated RF hypotheses."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import copy
import signal
import time
import numpy as np

from build_dsx01_orbit_modes import build_modes
from ds23_causal_phase_location import adjust_means
from ds23_feasible_position import feasible_fit
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_conditioned_relative_nomination import OUT as NOMINATIONS
from probe_ds23_joint_relative_position import OUT as JOINT,CASES,context,make,refit,relative_gates
from probe_ds23_joint_relative_feasible import slacks
from probe_ds23_frequency_events import cached,summary
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_ds23_combined_recovery_full import valid,ARMS

OUT=NOMINATIONS/'position'
VARIANTS=['conditioned_best','conditioned_strict']


def chosen_groups(nominations,variant):
    first=nominations['arms']['c0']['groups'];second={g['group']:g for g in nominations['arms']['fitted_c']['groups']};selected={}
    for group in first:
        if not group['selected']:continue
        best=group['best'];other=second[group['group']]
        if variant=='conditioned_strict':
            if not other['selected']:continue
            b=other['best']
            if [best[k+'_index'] for k in ['first','second']]!=[b[k+'_index'] for k in ['first','second']]:continue
            if any(g['qualified_runner_up_gap'] is None or g['qualified_runner_up_gap']<2*np.log(20) for g in [group,other]):continue
        selected[group['group']]={k:best[k] for k in ['first_index','second_index','first_norad','second_norad','difference_alias']}
    return selected


def context_selected(case,variant):
    d=context(case);nominations=read(NOMINATIONS/(case+'.json'));selection=chosen_groups(nominations,variant)
    if not selection:return None
    groups=[]
    for g in d['groups']:
        if g['group'] in selection:
            g=copy.deepcopy(g);g['nomination']=selection[g['group']];groups.append(g)
    labels=sorted({g['nomination'][k+'_index'] for g in groups for k in ['first','second']})
    scan=d['scan'];widths,receipts=phase_widths(scan,labels);means=forecast_phase_mean(receipts,d['model']['shrinkage'])
    if d['signed']['accepted']:means=adjust_means(means,receipts,d['model'],d['signed']['selection'])
    p=make(d,'c0',np.zeros(len(d['all_labels'])),False,float(np.sqrt(2)*300));owners={j:set() for j in labels}
    for g in groups:
        for role in ['first','second']:owners[g['nomination'][role+'_index']].add(tuple(g['lane'][:2]))
    supported=[j for j in labels if j in p.supported or (j not in p.labels and len(owners[j])>=2)]
    modes,metadata=build_modes(scan,labels,supported,'physical')
    result=dict(d,groups=groups,rf_labels=labels,all_labels=sorted(set(p.labels)|set(labels)),rf_means=np.asarray(means),
        rf_widths=widths*d['model']['multiplier'],rf_modes=modes,rf_supported=supported,rf_mode_metadata=metadata)
    result['selection']=selection;result['unresolved_RF_groups']=[g['group'] for g in d['groups'] if g['group'] not in selection]
    return result


def constrained(d,pair,bias):
    if valid(pair) and all(r['final_phase_change_s']<=.01 and all(g['compatible'] for g in r['relative_gates']) for r in pair.values()):return pair,False
    minima=[]
    for arm in ARMS:
        r=pair[arm];p=make(d,arm,np.asarray(r['joint_phase_reference']),True,bias);cached(p)
        minima.append(min(slacks(p,np.asarray(r['endpoint_east_north_km']),d['original_entries'],bias).values()))
    if min(minima)<-.25:return pair,False
    output={}
    for arm in ARMS:
        r=pair[arm];x=np.asarray(r['endpoint_east_north_km']);reference=np.asarray(r['joint_phase_reference']);history=[]
        for _ in range(5):
            p=make(d,arm,reference,True,bias);cached(p)
            fitted=feasible_fit(lambda z:p.calculate(z)['negative_twice_elbo'],
                lambda z:np.array(list(slacks(p,z,d['original_entries'],bias).values()))-.01,x,p.lower,p.upper,iterations=40)
            x=np.asarray(fitted['parameters']);phase=np.clip(p.state(x)['phases'][d['all_labels']],-15,15)
            history.append(dict(fit=fitted,phase_change_s=float(np.max(abs(phase-reference)))));reference=phase
        record=summary(p,x,d['original_entries']);c=p.calculate(x)
        record.update(history=history,final_phase_change_s=history[-1]['phase_change_s'],joint_phase_reference=p.joint_reference,
            coefficient=c['coefficient'],noise_precision=c['noise_precision'],relative_noise_precision=c['relative_noise_precision'],
            relative_gates=relative_gates(p,x,bias),normalization_constant=c['normalization_constant'])
        output[arm]=record
    return output,True


def one(case,variant):
    path=OUT/(case+'_'+variant+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('360s conditional joint paired fit cap')));signal.alarm(360)
    try:
        nominees=read(NOMINATIONS/(case+'.json'));incumbent=context_signed(case)[-2]['policy_arms']
        d=context_selected(case,variant) if nominees['status']=='complete' else None
        if d is None:result=dict(case=case,variant=variant,status='no_offer',accepted=False,original_incumbent=incumbent,policy_arms=incumbent)
        else:
            bias=float(np.sqrt(2)*300);pair={arm:refit(d,arm,True,bias) for arm in ARMS};pair,attempted=constrained(d,pair,bias)
            accepted=bool(valid(pair) and all(r['final_phase_change_s']<=.01 and all(g['compatible'] for g in r['relative_gates']) for r in pair.values()))
            result=dict(case=case,variant=variant,status='complete',accepted=accepted,arms=pair,original_incumbent=incumbent,
                policy_arms=pair if accepted else incumbent,bias_sigma_hz=bias,include_relative=True,
                selected_pairs=d['selection'],unresolved_RF_groups=d['unresolved_RF_groups'],constrained_refinement_attempted=attempted,
                all_original_hierarchical_Gamma_Student_orbit_radio_fragment_priors_restored=True,
                all_original_GLRT_and_predictive_data_after_same_full_RF_quarantine=True,
                actual_quarantine_receipt=d['quarantine_receipt'],fixed_nomination_sha256=sha(NOMINATIONS/(case+'.json')),
                unresolved_RF_density_is_position_independent_not_ranked_against_other_masks=True,
                original_gates_not_relaxed=True,no_GPS_future_TLE_new_RF_or_IQ=True,reference_position_used=False)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,variant=variant,status='failed',accepted=False,error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result);print(case,variant,result['status'],result['accepted'],result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);assert read(NOMINATIONS/'independent_numerical_audit.json')['all_passed']
    cases=read(NOMINATIONS/'protocol.json')['cases']
    protocol=dict(cases=cases,development_cases=CASES,variants=VARIANTS,default='conditioned_strict',
        fixed_nomination_execution_sha256=sha(NOMINATIONS/'execution.json'),original_causal_priors_restored=True,
        same_original_GLRT_IQ_quarantine_and_predictive_subsets_in_both_variants=True,
        no_RF_null_group_updates_position=True,original_incumbent_fallback_for_failure=True,
        phase_rounds=5,steps_per_round=48,near_gate_cutoff=-.25,constrained_rounds=5,constrained_steps=40,
        both_c_arms_same_nominations_masks_and_search_budget=True,workers=8,per_pair_seconds=360,
        cold_start_km=[0,0],region_width_km=25,no_GPS_future_TLE_new_RF_or_IQ=True,
        comparison_cohort_previously_inspected_by_other_algorithms_same_site=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_joint_relative_position.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('conditional joint position protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=8) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c,v) for c in cases for v in VARIANTS])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,positions_not_evaluated_yet=True))


if __name__=='__main__':main()
