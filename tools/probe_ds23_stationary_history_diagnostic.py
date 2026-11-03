"""Causal prefix spatial medians, conditional on an unverified stationary site.

This diagnostic is not an ALGO01 position estimate: it has no location-change
model or current-scan physical-gate replay. No supplied GPS is imported here.
"""

from pathlib import Path
import numpy as np
from probe_ds23_predictive_linear import OUT as GAUSSIAN
from probe_ds23_robust_predictive_linear import OUT
from run_algo01_ds23_sample import OUT as SOURCE,read,write,sha


def spatial_median(points,epsilon_km=1e-6):
    p=np.asarray(points,float)
    if p.ndim!=2 or p.shape[1]!=2 or not len(p) or not np.isfinite(p).all() or epsilon_km<=0:
        raise ValueError('finite nonempty horizontal points and positive smoothing scale required')
    # A median at an input point is certified by the convex subgradient ball.
    # This avoids slow Weiszfeld convergence at collinear/vertex solutions.
    certified=[]
    for candidate in p:
        d=p-candidate;distance=np.linalg.norm(d,axis=1);coincident=distance<=epsilon_km
        gradient=np.sum(d[~coincident]/distance[~coincident,None],axis=0)
        if np.linalg.norm(gradient)<=sum(coincident)+1e-12:certified.append(candidate)
    if certified:return np.mean(certified,axis=0),0
    x=p.mean(axis=0)
    for iteration in range(4096):
        w=1/np.maximum(np.linalg.norm(p-x,axis=1),epsilon_km)
        next_x=np.sum(p*w[:,None],axis=0)/sum(w)
        if np.linalg.norm(next_x-x)<1e-7:return next_x,iteration+1
        x=next_x
    raise ValueError('spatial median did not converge')


def causal_prefix(records):
    rows=sorted(records,key=lambda r:r['captured_utc_ns'])
    if len({r['captured_utc_ns'] for r in rows})!=len(rows):raise ValueError('unique observation times required')
    points=[];result=[]
    for row in rows:
        points.append(row['east_north_km']);x,iterations=spatial_median(points)
        result.append(dict(case=row['case'],captured_utc_ns=row['captured_utc_ns'],position_east_north_km=x,
            scans_used=len(points),latest_input_utc_ns=row['captured_utc_ns'],iterations=iterations))
    return result


def run():
    sample=read(SOURCE/'sample.json');cases=sample['selected'];results={};sources={}
    for method in ('baseline','gaussian','student_noise','student_noise_and_bias'):
        results[method]={}
        for arm in ('c0','fitted_c'):
            records=[]
            for member in cases:
                case=member['dataset_label'];path=(GAUSSIAN if method in ('baseline','gaussian') else OUT)/(case+'.json')
                data=read(path);sources[str(path)]=sha(path)
                pair=data['baseline_arms'] if method=='baseline' else data['results']['all_linear' if method=='gaussian' else method]['policy_arms']
                records.append(dict(case=case,captured_utc_ns=member['captured_utc_ns'],east_north_km=pair[arm]['endpoint_east_north_km']))
            results[method][arm]=dict(inputs=records,estimates=causal_prefix(records))
    write(OUT/'stationary_history_diagnostic.json',dict(results=results,input_sha256=sources,
        no_GPS_used=True,causal_prefix_invariance_tested=True,numerical_distance_floor_km=1e-6,
        same_single_station_assumption_unverified=True,no_motion_or_reset_model=True,
        no_current_scan_physical_gate_replay=True,not_an_ALGO01_or_full_DS23_result=True,
        source_sha256=sha(Path(__file__))))


if __name__=='__main__':run()
