"""RF-only diagnostic of point concentration inside accepted calibration curves."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import numpy as np

import run_ds23_dbg01_iteration_017 as runner
import inventory_ds23_calibration_curvature as cohort
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_23_ds23_residual_concentration'


def concentration(residual,sigma):
    r,s=np.asarray(residual,float),np.asarray(sigma,float)
    if r.ndim!=1 or len(r)<2 or s.shape!=r.shape or not np.isfinite(r).all() or not np.isfinite(s).all() or np.any(s<=0):
        raise ValueError('at least two finite residuals and positive matching noise required')
    energy=r*r;normalized=(r/s)**2;k=int(np.argmax(energy));j=int(np.argmax(normalized))
    return dict(points=len(r),RMS_hz=float(np.sqrt(energy.mean())),maximum_absolute_residual_hz=float(abs(r[k])),
        maximum_raw_energy_fraction=float(energy[k]/energy.sum()) if energy.sum() else 0.,maximum_raw_index=k,
        maximum_normalized_energy_fraction=float(normalized[j]/normalized.sum()) if normalized.sum() else 0.,maximum_normalized_index=j,
        diagnostic_RMS_without_maximum_hz=float(np.sqrt(max(0,float(energy.sum()-energy[k]))/(len(r)-1))),
        no_point_is_removed_and_no_new_fit=True)


def one(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('90s residual inventory cap')));signal.alarm(90)
    runner.configure();data=runner.engine.current_setup(case);rows=[]
    for arm,saved in data['arms'].items():
        p=runner.engine.baseline.build(data,arm,saved['phase_reference']);c=p.calculate(np.asarray(saved['endpoint_east_north_km']))
        for k,(row,index,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
            use=p.keep[sl]
            if use.sum()<2:continue
            track=data['scan'].tracks[index];r=c['conditional_residual_hz'][sl][use];sigma=p.point_noise[sl][use]
            e=concentration(r,sigma);ids=np.asarray(track['observation_ids'])[use].tolist();times=np.asarray(track['times'])[use]
            rows.append(dict(arm=arm,component=row['component'],norad=row['candidate_norad'],original_power=float(data['powers'][k]),
                original_group_precision=float(c['noise_precision'][k]),maximum_raw_time_s=float(times[e['maximum_raw_index']]),
                observation_ids=ids,times=times,residual_hz=r,sigma_hz=sigma,**e))
    write(OUT/(case+'.json'),dict(case=case,rows=rows,observations_sha256=sha(data['observations_path']),
        original_values_IDs_labels_aliases_masks_priors_and_results_unchanged=True))
    signal.alarm(0);print(case,'RF concentration inventory',len(rows),'curve arms',flush=True)
    return dict(case=case,status='complete',curve_arms=len(rows))


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve RF concentration inventory')
    random20=read(cohort.OUT/'protocol.json')['random20'];engineering=read(runner.RAW/'protocol.json')['cases'];cases=engineering+random20
    write(OUT/'protocol.json',dict(cases=cases,engineering=engineering,random20=random20,
        reused_ID_only_random20_protocol_sha256=sha(cohort.OUT/'protocol.json'),source_sha256=sha(Path(__file__)),
        original_incumbent_only_before_native_growth=True,both_c_arms=True,RF_statistics_only_no_accuracy_or_new_fit=True,
        metrics='largest raw and RF-sigma-standardized squared residual fraction; descriptive RMS excluding largest raw residual',
        no_point_or_curve_deletion_no_model_or_gate_change=True,
        rationale='one fragment-wide Gamma precision can downweight every point when one point dominates its energy',
        diagnostic_not_proof_of_an_outlier_or_a_new_noise_model=True,no_GPS_following_TLE_new_RF_or_IQ=True,workers=4))
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True))


if __name__=='__main__':main()
