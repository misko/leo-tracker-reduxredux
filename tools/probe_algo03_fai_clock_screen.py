"""Fixed-RF-position screen of physical channel clock steps and a phase control."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from ds23_fai_clock import clock_problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_frame_peak_recovery import context
from probe_ds23_causal_phase_mean import forecast_phase_mean
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_19_algo03_fai_clock_screen'


def run(case):
    scan,node,mask,base,old=context(case);model=old['hyperparameters_from_pre_RF_TLE_only']
    powers=np.asarray(old['weights']);_,receipts=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipts,model['shrinkage']);results={};started=time.monotonic()
    for name,sigma,phase in [('zero_clock_replay',0.,12.),('FAI_candidate',50.,12.),('phase_control',50.,7.)]:
        pair={}
        for arm in ('c0','fitted_c'):
            original=old['curved_arms'][arm];x=np.asarray(original['endpoint_east_north_km'])
            reference=np.asarray(original['phase_reference']);history=[]
            for _ in range(3):
                p=clock_problem(scan,node,mask,arm,reference,powers,means,model,
                    sigma_hz=sigma,utc_boundary_phase_s=phase)
                next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
                history.append(float(max(abs(next_phase-reference))));reference=next_phase
            c=p.calculate(x);gates=retained_metrics(p,x)
            pair[arm]=dict(fixed_RF_position_km=x,negative_twice_elbo=c['negative_twice_elbo'],
                change_from_original_curved_ELBO=c['negative_twice_elbo']-original['negative_twice_elbo'],
                gates=gates,phase_changes_s=history,clock_keys=c['clock_keys'],
                clock_offset_posterior_hz=c['clock_offset_posterior_hz'],
                RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][mask]**2))))
        results[name]=dict(arms=pair)
        print(case,name,{a:round(r['change_from_original_curved_ELBO'],3) for a,r in pair.items()},flush=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,seconds=time.monotonic()-started,
        no_GPS_postscan_TLE_or_position_update=True,position_fixed_to_original_RF_curved_estimate=True,
        same_observations_aliases_nominations_noise_powers_and_other_priors=True,
        paired_c0_fitted_c=True,clock_sigma_hz=50.,
        phase12_is_candidate_UTC_phase_not_a_demonstrated_transmitter_clock=True,
        shared_same_satellite_same_RF_is_beam_approximation_needing_validation=True))
    return dict(case=case,seconds=time.monotonic()-started)


def main():
    if OUT.exists():
        raise FileExistsError('preserve fixed-position screen')
    OUT.mkdir();cases=['DS23-0202','DS23-0274']
    write(OUT/'protocol.json',dict(cases=cases,workers=2,source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/ds23_fai_clock.py'),
        no_GPS_or_position_optimization=True,no_linear_calibration_points=True,
        sigma_hz=50.,UTC_phase_candidate_s=12.,UTC_phase_control_s=7.,
        original_zero_sigma_replay_required=True))
    results=[]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for future in as_completed([executor.submit(run,c) for c in cases]):
            results.append(future.result())
    write(OUT/'execution.json',dict(results=results))


if __name__=='__main__':
    main()
