"""Matched integrated-height ablation on archived or remeasured DS23 curves."""

import argparse
import time
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_height_problem import make_height_problem,exact_height_replay,height_uncertainty
from ds23_heteroscedastic_gates import metrics
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_timestamps import apply_effective_times
from prototype_dsx01_continuous_position import latlon
from remeasure_ds23_rx2_cohort import OUT as MEASURED
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_height_uncertainty'
SIGMAS=(0.,300.,1000.)


def context(case,scope):
    learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution']
    node=read(SOURCE/case/'result.json')['final_node'];keep=np.array(primary['mask'],bool)
    model=learned['hyperparameters_from_pre_RF_TLE_only'];scan=final_scan(case)
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    base=problem(scan,node,'c0',keep);_,receipts=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipts,model['shrinkage']);noise={}
    if scope=='refined':
        raw=read(MEASURED/(case+'_refined.json'))
        noise=read(MEASURED/(case+'_refined_local_noise_position.json'))['proposed_noise_by_id']
        update_values(scan,raw['rows'],'joint_CFO_epoch_rate');apply_effective_times(scan,raw['rows'])
    return scan,node,keep,powers,means,model,noise,primary['arms']


def refit(scan,node,keep,powers,means,model,noise,arm,sigma,scope):
    reference=np.zeros(len(means));height=0.;orbit=None;x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_height_problem(scan,node,keep,arm,reference,powers,means,model,noise,sigma,height,orbit)
        r=fit(p,x,iterations=48);x=np.array(r['parameters']);c=p.calculate(x)
        next_height=c['height_posterior_mean_m'];next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=r,height_reference_m=height,height_m=next_height,
            height_change_m=next_height-height,phase_change_s=float(max(abs(next_phase-reference)))))
        reference=next_phase;height=next_height
        orbit=c['coefficient'][p.height_orbit_start:p.height_index]
    c=p.calculate(x);replay=exact_height_replay(p,x)
    gates=metrics(p,x) if scope=='refined' else retained_metrics(p,x)
    valid_geometry=replay['maximum_difference_in_point_noise_units']<=.1 and abs(replay['height_reference_difference_m'])<=.5
    height_physical=-500<=height<=9000
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),state=p.state(x),phase_reference=p.reference,
        history=history,height_sigma_m=sigma,height_mean_m=height,height_reference_m=p.height_reference_m,
        exact_geometry_replay=replay,geometry_replay_qualified=valid_geometry,height_engineering_bounds_pass=height_physical,
        approximate_covariance=height_uncertainty(p,x,powers),active_points=int(keep.sum()),gates=gates,
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        negative_twice_elbo=c['negative_twice_elbo'],height_standardized_coefficient=float(c['coefficient'][p.height_index]),
        Gaussian_height_penalty=float(c['coefficient'][p.height_index]**2),
        height_complexity_is_in_integrated_logvolume=True)


def run(case,scope):
    started=time.monotonic();directory=OUT/scope;directory.mkdir(parents=True,exist_ok=True)
    if (directory/(case+'.json')).exists():raise FileExistsError('preserve scientific outputs')
    scan,node,keep,powers,means,model,noise,baseline=context(case,scope);results={}
    for sigma in SIGMAS:
        arms={arm:refit(scan,node,keep,powers,means,model,noise,arm,sigma,scope) for arm in ('c0','fitted_c')}
        valid=all(a['geometry_replay_qualified'] and a['height_engineering_bounds_pass'] and
                  all(t['compatible'] for t in a['gates']['tracks']) for a in arms.values())
        results[str(int(sigma))]=dict(arms=arms,paired_valid=valid)
        write(directory/(case+'_partial.json'),dict(case=case,scope=scope,results=results))
        print(case,scope,'height SD',sigma,'paired valid',valid,flush=True)
    reference=(baseline if scope=='archived' else read(MEASURED/(case+'_refined_local_noise_position.json'))['policy_arms'])
    policies={name:r['arms'] if r['paired_valid'] else reference for name,r in results.items()}
    eligible=[name for name,r in results.items() if r['paired_valid']]
    selected=min(eligible,key=lambda name:results[name]['arms']['c0']['negative_twice_elbo']) if eligible else None
    write(directory/(case+'.json'),dict(case=case,scope=scope,results=results,policy_arms=policies,
        selected=selected,selected_arms=reference if selected is None else results[selected]['arms'],baseline_arms=reference,
        original_mask=keep,powers=powers,source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_height_problem.py'),
        learned_sha256=sha(LEARNED/(case+'.json')),no_GPS_used=True,no_IQ_reread=True,
        original_points_aliases_labels_other_priors_preserved=True,both_c_arms_same_height_hypothesis_and_budget=True,
        Gaussian_mean_zero_SD_300_or_1000_is_engineering_prior_not_survey=True,
        height_mean_engineering_bounds_m=[-500,9000],five_phase_and_height_refresh_rounds_48_steps=True,
        selection_by_full_normalized_c0_ELBO_among_paired_qualified_hypotheses=True,seconds=time.monotonic()-started))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    parser.add_argument('--scope',choices=['archived','refined'],required=True);args=parser.parse_args()
    run(args.case,args.scope)
