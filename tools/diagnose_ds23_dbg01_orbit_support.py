"""Counterfactual physical orbit support, never an association acceptance rule."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import probe_ds23_family_cavity_nominations as nomination
from probe_ds23_single_curved_reentry import predictive_track_data
from ds23_family_cavity import predictive_density_reference
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
import run_ds23_dbg01_iteration_002 as context
from run_algo01_ds23_sample import ROOT,read,write,sha

RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_003_raw'


def curvature_information(times,modes,covariance):
    t=np.asarray(times);m=np.asarray(modes);c=np.asarray(covariance)
    affine=np.column_stack((np.ones(len(t)),t-np.mean(t)))
    inverse=np.linalg.inv(c);cross=inverse@affine
    projected=inverse-cross@np.linalg.solve(affine.T@cross,cross.T)
    matrix=m.T@projected@m
    return np.maximum(0,np.linalg.eigvalsh((matrix+matrix.T)/2))


def one(case):
    d=context.current_setup(case);x=np.asarray(d['arms']['c0']['endpoint_east_north_km']);d=dict(d,x=x)
    p=context.baseline.build(d,'c0',d['arms']['c0']['phase_reference'])
    old_active={r['candidate_index'] for r,sl in zip(p.rows,p.slices) if p.keep[sl].any()}
    source=RAW/'all_curve_families'/(case+'_nominations.json');targets=read(source)['targets'];rows=[]
    for target in targets:
        best=target['best']
        if best is None or best['candidate_index'] in old_active or best['physical_modes']:
            continue
        data=predictive_track_data(d,p,x,target['row_index']);capture=[];original=nomination.gaussian_prediction
        def record(raw,features,covariance,sigma):
            capture.append((raw.copy(),features.copy(),covariance.copy(),sigma.copy()))
            return original(raw,features,covariance,sigma)
        nomination.gaussian_prediction=record
        try:
            result=nomination.candidate_prediction(d,dict(data,held_owners=2),best['candidate_index'],best['aliases'])
        finally:
            nomination.gaussian_prediction=original
        raw,features,covariance,sigma=capture[-1]
        direct,method=predictive_density_reference(raw,features,covariance,sigma)
        if abs(direct-result['score'])>2e-3:raise ValueError('counterfactual density failed independent replay')
        nb=data['radio_width'];physical=np.arange(nb+1,nb+4)
        other=np.array([k for k in range(features.shape[1]) if k not in physical])
        rest=np.diag(sigma*sigma)+features[:,other]@covariance[np.ix_(other,other)]@features[:,other].T
        eigen=curvature_information(data['times'],features[:,physical],rest)
        rows.append(dict(component=target['target']['component'],norad=best['norad'],points=len(data['times']),
            actual_curved_owners=data['held_owners'],counterfactual_two_owner_flag_only_enables_existing_three_physical_modes=True,
            current_prediction=best,counterfactual_prediction=result,
            physical_prior_curvature_information_eigenvalues=eigen,
            physical_coefficient_norm=float(np.linalg.norm(np.asarray(result['coefficient'])[physical])),
            noise={k:v[0] for k,v in batch_noise_screen(np.asarray(result['residual_hz'])[None,:],data['times']).items()},
            independent_density_difference=abs(direct-result['score']),independent_method=method))
    result=dict(case=case,rows=rows,diagnostic_only_no_association_or_position_adoption=True,
        actual_owner_counts_are_not_changed_in_inference=True,
        no_GPS_or_following_TLE_or_new_prior_scale_used=True,source_sha256=sha(Path(__file__)),
        input_nominations_sha256=sha(source),all_passed=True)
    write(RAW/'orbit_support_diagnostic'/(case+'.json'),result)
    for r in rows:
        print(case,r['component'].split('-RF')[0],r['norad'],
            'RMS',r['current_prediction']['conditional_RMS_hz'],r['counterfactual_prediction']['conditional_RMS_hz'],
            'curvature eigen',r['physical_prior_curvature_information_eigenvalues'],
            'coef norm',r['physical_coefficient_norm'],flush=True)
    return dict(case=case,all_passed=True,diagnostic_curves=len(rows))


def main():
    global RAW
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--raw',type=Path,default=RAW)
    args=parser.parse_args();RAW=args.raw;context.RAW=RAW;context.configure()
    out=RAW/'orbit_support_diagnostic';out.mkdir(exist_ok=True)
    if (out/'execution.json').exists():raise FileExistsError('preserve counterfactual diagnostic')
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,read(RAW/'protocol.json')['cases']))
    write(out/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True,
                                  no_algorithm_support_gate_changed=True))


if __name__=='__main__':main()
