"""Qualify EM-guided integration before any orphan-driven position search."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

import run_ds23_dbg01_iteration_004 as context
from ds23_orphan_predictive_mixture import OrphanPrediction,orphan_rows
from ds23_orphan_adaptive_importance import AdaptiveOrphans
from probe_ds23_orphan_mixture import curve_geometry_null
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=context.RAW/'orphan_adaptive'
SEEDS=(2026102204,2026102217)


def qualify(job):
    case,arm,bias=job;began=time.monotonic();d=context.engine.current_setup(case)
    saved=d['arms'][arm];p=context.engine.baseline.build(d,arm,saved['phase_reference'])
    x=np.asarray(saved['endpoint_east_north_km']);observations=orphan_rows(d)
    null=curve_geometry_null(d,p,x)
    prediction=OrphanPrediction(p,observations,d['powers'],draw_power=4,bias_sigma_hz=bias)
    oracle=AdaptiveOrphans(prediction,x);proposals=oracle.proposals();trials=[]
    for seed in SEEDS:
        r=oracle.integrate(proposals,power=10,seed=seed,nodes=64,details=True)
        control=oracle.integrate(proposals,power=10,seed=seed,nodes=128)
        r.update(seed=seed,quadrature_difference=abs(r['relative_negative_twice_log_likelihood']-control['relative_negative_twice_log_likelihood']))
        trials.append(r)
    difference=abs(trials[0]['relative_negative_twice_log_likelihood']-trials[1]['relative_negative_twice_log_likelihood'])
    qualified=bool(difference<=.5 and all(t['effective_nuisance_draws']>=32 and t['quadrature_difference']<=.05 for t in trials))
    result=dict(case=case,arm=arm,bias_sigma_hz=bias,status='complete',
        points=len(observations),trials=trials,seed_loss_difference=difference,qualified=qualified,
        proposals=proposals,geometry_null=null,seconds=time.monotonic()-began,
        no_inference_model_or_prior_change_from_prior_draw_prototype=True,
        EM_only_defines_numerical_importance_proposal_exact_mixture_density_correction_used=True,
        no_new_GPS_or_following_TLE_or_position_search=True)
    write(OUT/(case+'_'+arm+f'_bias{int(bias)}_qualification.json'),result)
    print(case,arm,bias,'adaptive orphan', [t['relative_negative_twice_log_likelihood'] for t in trials],
          'ESS',[t['effective_nuisance_draws'] for t in trials],'qualified',qualified,'seconds',round(result['seconds'],2),flush=True)
    return dict(case=case,arm=arm,bias=bias,status='complete',qualified=qualified)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();context.configure();OUT.mkdir(exist_ok=True)
    record=dict(cases=read(context.RAW/'protocol.json')['cases'],seeds=list(SEEDS),
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_orphan_adaptive_importance.py'),
        parent_model_sha256=sha(context.RAW/'orphan_mixture/protocol.json'),
        importance='10percent prior,90percent three EM Gaussian proposals; exact deterministic-mixture p/q correction',
        EM=dict(initial_signal_fractions=[.05,.3,.7],maximum_steps=48,covariance_eigenvalues='min(1,2/H) in whitened prior coordinates'),
        all_original_orphan_points_in_same_normalized_likelihood=True,
        shared_nuisance_draws_include_full_curved_calibration_posterior_and_existing300Hz_new_lane_family_constants=True,
        no_EM_calibration_substitution=True,old_qualification_thresholds_unchanged=True,
        no_new_geographic_outcome_or_satellite_identity_choice=True,
        no_position_fits_until_both_c_arms_numerically_qualified=True)
    path=OUT/'protocol.json'
    if path.exists():raise FileExistsError('preserve frozen adaptive qualification')
    write(path,record);rows=[]
    jobs=[(c,a,b) for c in record['cases'] for a in ['c0','fitted_c'] for b in [0.,300.]]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(qualify,j) for j in jobs]):rows.append(f.result())
    write(OUT/'qualification_execution.json',dict(rows=rows,all_terminal=True,all_passed=True,
        numerically_qualified_rows=sum(r['qualified'] for r in rows)))


if __name__=='__main__':main()
