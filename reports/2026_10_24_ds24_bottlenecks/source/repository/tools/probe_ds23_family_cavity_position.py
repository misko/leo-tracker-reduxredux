"""Full-evidence causal position tests of covariance-aware active-family offers."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import copy
import itertools
from pathlib import Path
import signal
import time
import numpy as np

from ds23_family_cavity import unused_student_gap,legacy_phase_reference
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_frequency_events import refit
from probe_ds23_family_cavity_nominations import OUT as NOMINATIONS,CASES,setup
from probe_ds23_gate_retention_cohort import constrained
from run_ds23_combined_recovery_full import valid,ARMS
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=NOMINATIONS/'position'


def unused_count(p,entries):
    active={r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}
    active.update(e['candidate_index'] for e in entries)
    return len(set(p.labels)-active)


def configuration(d,offers):
    node=copy.deepcopy(d['node']);entries=copy.deepcopy(d['entries']);scan=d['scan']
    changes={}
    for family,offer in offers:
        target=family['original_index'];candidate=offer['candidate_index'];lookup={m['component']:int(a) for m,a in zip(family['members'],offer['aliases'],strict=True)}
        if target in changes:raise ValueError('each original family can be replaced only once')
        changes[target]=(candidate,lookup)
    # Resolve every replacement against the original labels. A->B and B->A
    # must not relabel the already changed A rows a second time.
    for k,(original,row) in enumerate(zip(d['node']['seed']['rows'],node['seed']['rows'],strict=True)):
        if original['candidate_index'] in changes:
            candidate,lookup=changes[original['candidate_index']]
            row.update(candidate_index=candidate,candidate_norad=int(scan.norads[candidate]))
            if row['component'] in lookup:node['aliases'][k]=lookup[row['component']]
    for original,entry in zip(d['entries'],entries,strict=True):
        if original['candidate_index'] in changes:
            candidate,lookup=changes[original['candidate_index']]
            entry.update(candidate_index=candidate,norad=int(scan.norads[candidate]),alias=lookup[entry['component']])
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
    if set(e['candidate_index'] for e in entries)-set(labels):raise ValueError('predictive candidate lacks original model coordinate')
    return node,entries,d['all_means'][labels]


def fit_configuration(d,node,entries,means):
    """Fit an explicit research hypothesis under the unchanged final model."""
    pair={arm:refit(d['scan'],node,d['keep'],arm,d['powers'],means,d['model'],[],entries) for arm in ARMS}
    attempted=False
    if not valid(pair):
        minima=[]
        for arm in ARMS:
            r=pair[arm];p=make_event_problem(d['scan'],node,d['keep'],arm,np.asarray(r['phase_reference']),d['powers'],means,d['model'],[])
            attach_event_predictive(p,entries,d['powers']);minima.append(min(gate_slacks(p,np.asarray(r['endpoint_east_north_km']),entries).values()))
        if min(minima)>=-.25:
            pair=constrained(d['scan'],node,d['keep'],d['powers'],means,d['model'],entries,pair);attempted=True
    for arm,r in pair.items():
        p=make_event_problem(d['scan'],node,d['keep'],arm,np.asarray(r['phase_reference']),d['powers'],means,d['model'],[])
        attach_event_predictive(p,entries,d['powers']);c=p.calculate(np.asarray(r['endpoint_east_north_km']))
        r.update(coefficient=c['coefficient'],unused_phase_coordinates=unused_count(p,entries),
            corrected_selection_loss=r['negative_twice_elbo']-unused_count(p,entries)*unused_student_gap(d['model']['nu']))
    return dict(arms=pair,paired_valid=bool(valid(pair) and all(r['final_phase_change_s']<=.01 for r in pair.values())),
        node=node,entries=entries,means=means,constrained_refinement_attempted=attempted)


def trial(d,offers):
    result=fit_configuration(d,*configuration(d,offers))
    result['replacements']=[dict(original_index=f['original_index'],original_norad=f['original_norad'],candidate_index=o['candidate_index'],
        norad=o['norad'],predictive_gain=f['original']['score']-o['score']) for f,o in offers]
    return result


def one(case,nominations_dir=None,output_dir=None):
    source=NOMINATIONS if nominations_dir is None else Path(nominations_dir)
    path=(OUT if output_dir is None else Path(output_dir))/(case+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('540s cavity full evidence position cap')));signal.alarm(540)
    try:
        d=setup(case);nom=read(source/(case+'_nominations.json'));baseline=d['signed']['policy_arms'];replay={};base_corrected={};reference_repairs={}
        for arm,r in baseline.items():
            p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(r['phase_reference']),d['powers'],d['means'],d['model'],[])
            attach_event_predictive(p,d['entries'],d['powers']);c=p.calculate(np.asarray(r['endpoint_east_north_km']))
            delta=c['negative_twice_elbo']-r['negative_twice_elbo']
            if abs(delta)>=1e-5:
                np.testing.assert_allclose(r['phase_reference'],np.asarray(r['state']['phases'])[p.labels],rtol=0,atol=1e-12)
                def posterior(reference,parameters):
                    probe=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[])
                    return probe.state(parameters)['phases'][probe.labels]
                reference=legacy_phase_reference(r['history'],np.zeros(len(d['means'])),posterior)
                p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[])
                attach_event_predictive(p,d['entries'],d['powers']);c=p.calculate(np.asarray(r['endpoint_east_north_km']))
                reference_repairs[arm]=dict(archived_reference=np.asarray(r['phase_reference']),replayed_fit_reference=reference,
                    original_loss_difference=delta,loss_difference_after_replay=c['negative_twice_elbo']-r['negative_twice_elbo'],
                    reconstructed_from_saved_phase_round_endpoints_without_position_refitting=True)
                delta=c['negative_twice_elbo']-r['negative_twice_elbo']
            assert abs(delta)<1e-5
            replay[arm]=delta;base_corrected[arm]=r['negative_twice_elbo']-unused_count(p,d['entries'])*unused_student_gap(d['model']['nu'])
        families=sorted([f for f in nom['families'] if f['best'] is not None and f['predictive_gain']>0],key=lambda f:f['predictive_gain'],reverse=True)[:4]
        offers=[(f,f['best']) for f in families];hypotheses=[[o] for o in offers]
        if len(offers)>=2:hypotheses.append(offers[:2])
        # Both directions of simultaneous exchanges must be simultaneous, not
        # sequential relabeling of already changed rows; skip dependent targets.
        hypotheses=[h for h in hypotheses if not ({f['original_index'] for f,o in h}&{o['candidate_index'] for f,o in h})]
        trials=[]
        for hypothesis in hypotheses:
            record=trial(d,hypothesis);trials.append(record)
            print(case,'trial',record['replacements'],'valid',record['paired_valid'],flush=True)
        candidates=[r for r in trials if r['paired_valid']]
        best=min(candidates,key=lambda r:r['arms']['c0']['corrected_selection_loss']) if candidates else None
        penalty=float(2*np.log(max(1,len(d['scan'].norads)*len(nom['families']))))
        gain=base_corrected['c0']-best['arms']['c0']['corrected_selection_loss'] if best else None
        accepted=bool(best is not None and gain>penalty)
        result=dict(case=case,status='complete',accepted=accepted,trials=trials,selected=best if accepted else None,
            baseline_arms=baseline,policy_arms=best['arms'] if accepted else baseline,baseline_corrected_loss=base_corrected,
            search_penalty=penalty,selection_gain=gain,original_mask=d['keep'],powers=d['powers'],model=d['model'],
            baseline_node=d['node'],baseline_entries=d['entries'],baseline_means=d['means'],
            same_full_original_observations_and_physical_priors_in_all_trials=True,
            original_aliases_changed_only_in_explicit_complete_family_hypotheses=True,
            original_both_arm_residual_gates_required=True,unused_student_prior_gap_removed_only_if_no_curved_or_predictive_data=True,
            null_objective_replay_differences=replay,no_GPS_RF_future_TLE_or_point_deletion=True,
            legacy_fit_reference_replay=reference_repairs,
            nomination_sha256=sha(source/(case+'_nominations.json')))
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',accepted=False,error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result);return result


def main():
    OUT.mkdir(exist_ok=True);assert read(NOMINATIONS/'nomination_execution.json')['all_terminal']
    protocol=dict(cases=CASES,workers=3,per_case_seconds=540,max_positive_families=4,include_top_two_joint_replacement=True,
        preserve_all_original_GLRT_and_predictive_points=True,prior_hyperparameters_noise_and_likelihood_powers_unchanged=True,
        all_trials_cold_start=[0,0],regional_width_km=25,phase_rounds=5,position_steps=48,
        constrained_rounds=5,constrained_steps=40,minimum_slack_for_refinement=-.25,
        adoption='paired gates, phase convergence and corrected normalized c0 gain greater than2log(catalogue size*families)',
        no_GPS_RF_or_future_TLE_used=True,
        nominations_sha256=sha(NOMINATIONS/'nomination_execution.json'),source_sha256=sha(Path(__file__)))
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('family cavity position protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=3) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c) for c in CASES])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,no_geographic_error_evaluation_yet=True))


if __name__=='__main__':main()
