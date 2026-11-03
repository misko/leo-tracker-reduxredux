"""Matched Gamma-noise prediction on top of the published causal signed prior."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from ds23_hierarchical_predictive import attach_hierarchical_predictive
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo03_frame_peak_recovery import context, SOURCE
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_frequency_events import cached, summary
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT=ROOT/'reports/2026_10_20_ds23_hierarchical_predictive'
LOCATION=ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'
ARMS=('c0','fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (
        ROOT/'tools/probe_ds23_hierarchical_predictive.py',
        ROOT/'tools/ds23_hierarchical_predictive.py', ROOT/'tools/dsx01_hierarchical_bound.py')}


def prepare():
    OUT.mkdir(exist_ok=True)
    path=OUT/'protocol.json'
    if path.exists():
        protocol=read(path)
        if protocol['source_sha256']!=hashes():raise ValueError('frozen predictive study changed')
        return protocol
    cases=read(ROOT/'reports/2026_10_20_ds23_causal_phase_location_validation/protocol.json')['cases']
    protocol=dict(cases=cases,workers=20,incumbent='published signed-prior policy with original fallbacks',
        hypothesis='integrate existing unseen Gamma(2,2) predictive noise instead of fixed Gaussian variance inflation',
        predictive_noise_nu=4,per_track_constant_prior_sigma_hz=300.,
        full_shared_curved_calibration_covariance_retained=True,linear_observations_never_update_calibration=True,
        all_original_observations_masks_labels_aliases_powers_other_priors_and_gates_retained=True,
        same_prior_masks_and_cold_5x48_budget_in_c0_and_fitted_c=True,
        maximum_predictive_precision_change=1e-4,
        adoption='all original paired gates and variational convergence; normalized RF gain >2log(2) in both controls',
        no_GPS_future_TLE_new_RF_or_IQ_remeasurement=True,
        cohort_preselected_random20_at_same_site_not_new_location_validation=True,
        source_sha256=hashes())
    write(path,protocol)
    return protocol


def run(case):
    prepare()
    directory=OUT/case
    directory.mkdir(exist_ok=True)
    if (directory/'result.json').exists():return dict(case=case,cached=True)
    scan,node,keep,base,old=context(case)
    evidence=read(LOCATION/'evaluation_audit.json')['evidence'][case]
    loc_path=ROOT/evidence['path']
    if sha(loc_path)!=evidence['sha256']:raise ValueError('published prior evidence changed')
    loc=read(loc_path)
    if loc['baseline_arms']!=old['policy_arms'] or loc['original_mask']!=old['mask']:
        raise ValueError('published incumbent uses different measurements')
    model=old['hyperparameters_from_pre_RF_TLE_only']
    _,receipts=phase_widths(scan,base.labels)
    means=np.asarray(loc['means_s']) if loc['accepted'] else forecast_phase_mean(receipts,model['shrinkage'])
    incumbent=loc['policy_arms']
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    powers=np.asarray(old['weights'])
    started=time.monotonic()
    pair={}
    for arm in ARMS:
        reference=np.zeros(len(means))
        x=np.zeros(2)
        history=[]
        for epoch in range(5):
            p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
            attach_hierarchical_predictive(p,entries,powers)
            p.events=[]
            cached(p)
            fitted=fit(p,x,iterations=48)
            x=np.asarray(fitted['parameters'])
            phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
            change=float(np.max(abs(phase-reference)))
            history.append(dict(epoch=epoch,fit=fitted,phase_change_s=change))
            reference=phase
        c=p.calculate(x)
        pair[arm]=dict(summary(p,x,entries),history=history,final_phase_change_s=change,
            predictive_noise_precision=c.get('linear_noise_precision',[]),
            predictive_precision_iterations=c.get('linear_precision_iterations',0),
            predictive_precision_change=c.get('linear_precision_change',0.))
    valid=pair_passes(pair,include_linear=True) and all(
        r['predictive_precision_change']<=1e-4 and r['linear_calibration_max_difference']<=1e-12 for r in pair.values())
    gains={a:incumbent[a]['negative_twice_elbo']-pair[a]['negative_twice_elbo'] for a in ARMS}
    accepted=bool(valid and entries and all(g>2*np.log(2) for g in gains.values()))
    write(directory/'result.json',dict(case=case,arms=pair,paired_valid=valid,accepted=accepted,
        policy_name='hierarchical_predictive' if accepted else 'signed_incumbent',
        policy_arms=pair if accepted else incumbent,baseline_arms=old['policy_arms'],incumbent_arms=incumbent,
        RF_gains_vs_incumbent=gains,model_search_penalty=2*np.log(2),
        mask=keep,entries=entries,means_s=means,powers=powers,
        baseline_sha256=sha(SOURCE/case/'algo02_result.json'),incumbent_sha256=sha(loc_path),
        source_sha256=hashes(),GPS_used=False,future_TLE_used=False,seconds=time.monotonic()-started))
    print(case,'valid',valid,'accepted',accepted,'RF gains',gains,flush=True)
    return dict(case=case,valid=valid,accepted=accepted,seconds=time.monotonic()-started)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case')
    args=parser.parse_args()
    protocol=prepare()
    if args.case:
        run(args.case)
        return
    receipts=[]
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        futures={pool.submit(run,c):c for c in protocol['cases']}
        for future in as_completed(futures):
            try:receipts.append(future.result())
            except Exception as exc:receipts.append(dict(case=futures[future],error=repr(exc)))
            write(OUT/'progress.json',dict(completed=len(receipts),total=len(futures),receipts=receipts))
    write(OUT/'execution.json',dict(all_terminal=True,receipts=receipts))


if __name__=='__main__':main()
