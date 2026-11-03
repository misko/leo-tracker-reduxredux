"""Paired-c position test of reception-time Doppler with fixed original data."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from ds23_reception_geometry import reception_problem,attach_reception_predictions
from ds23_feasible_position import noise_slacks
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo03_frame_peak_recovery import context
from probe_ds23_causal_phase_mean import forecast_phase_mean
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import profile

OUT=ROOT/'reports/2026_10_20_algo03_reception_position'


def refit(scan,node,keep,powers,means,model,arm,entries,enabled):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=reception_problem(scan,node,keep,arm,reference,powers,means,model,enabled=enabled)
        attach_reception_predictions(p,entries,powers,enabled=enabled)
        result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=phase
    c=p.calculate(x);curved=p.curved_calculate(x) if entries else c;gates=[]
    for e,sl in zip(entries,getattr(p,'linear_slices',[]),strict=True):
        t=scan.tracks[e['track_index']];raw=c['linear_raw_prediction_residual_hz'][sl]
        terms=profile(raw,np.zeros(len(raw)),*scan.white[e['track_index']],bias_sigma=300.)
        valid=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0
            and min(noise_slacks(terms['innovations'][0],t['times']).values())>=0 and min(c['linear_elevation'][sl])>=0)
        gates.append(dict(component=e['component'],compatible=valid,points=e['points'],observation_ids=e['observation_ids']))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,
        phase_reference=p.reference,state=p.state(x),gates=retained_metrics(p,x),linear_gates=gates,
        active_points=int(keep.sum()),additional_predictive_points=sum(e['points'] for e in entries),
        final_phase_change_s=history[-1]['phase_change_s'],
        negative_twice_elbo=c['negative_twice_elbo'],curved_negative_twice_elbo=curved['negative_twice_elbo'],
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        linear_calibration_max_difference=float(max(abs(c['coefficient']-curved['coefficient']))),
        correction_rms_hz=float(np.sqrt(np.mean(c.get('reception_correction_hz',np.zeros(len(keep)))[keep]**2))))


def run(case,null=False):
    path=OUT/(case+('_null' if null else '')+'.json')
    if path.exists():
        raise FileExistsError('preserve reception experiment')
    scan,node,keep,base,old=context(case);model=old['hyperparameters_from_pre_RF_TLE_only']
    powers=np.asarray(old['weights']);_,receipt=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipt,model['shrinkage'])
    entries=old['linear_entries'] if old['linear_paired_valid'] else []
    started=time.monotonic()
    pair={arm:refit(scan,node,keep,powers,means,model,arm,entries,not null) for arm in ('c0','fitted_c')}
    valid=pair_passes(pair,include_linear=True)
    write(path,dict(case=case,null_control=null,trial_arms=pair,paired_valid=valid,
        policy_arms=pair if valid else old['policy_arms'],baseline_arms=old['policy_arms'],
        causal_TLEs_original_observations_labels_aliases_noise_powers_and_priors_unchanged=True,
        no_GPS_or_new_prior_used_for_inference=True,
        phase_and_three_state_mode_derivatives_use_same_reception_kernel=True,
        linear_calibration_feedback_absent_and_original_entries_retained=True,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_reception_geometry.py'),
        seconds=time.monotonic()-started))
    print(case,'null',null,'qualified',valid,'seconds',time.monotonic()-started,flush=True)
    return dict(case=case,null_control=null,paired_valid=valid,seconds=time.monotonic()-started)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case');parser.add_argument('--null',action='store_true')
    args=parser.parse_args()
    if args.case:
        OUT.mkdir(exist_ok=True);run(args.case,args.null);return
    if OUT.exists():
        raise FileExistsError('preserve sealed reception experiment')
    OUT.mkdir();cases=read(ROOT/'reports/2026_10_19_algo03_frame_predictive_v2/protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,workers=20,phase_rounds=5,position_steps=48,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_reception_geometry.py'),
        original_reception_kernel_sha256=sha(ROOT/'tools/dsx01_reception_doppler.py'),
        new_parameters=0,fixed_earth_monopole_relativistic_control=True,
        matched_c0_and_fitted_c=True,original_curved_and_predictive_evidence_retained=True,
        GPS_not_used_for_inference=True,unchanged_noise_priors_thresholds_and_cold_start=True))
    started=time.monotonic();receipts=[]
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures=[executor.submit(run,c) for c in cases]
        for future in as_completed(futures):
            receipts.append(future.result())
    write(OUT/'execution.json',dict(receipts=receipts,seconds=time.monotonic()-started,all_terminal=True))


if __name__=='__main__':main()
