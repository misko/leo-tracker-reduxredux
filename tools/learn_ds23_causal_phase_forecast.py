"""Select signed phase-forecast shrinkage using only pre-RF TLE transitions."""

import argparse
import math
from pathlib import Path

import numpy as np
from sgp4.api import Satrec

from investigate_ds23_adaptive_failures import causal_phase_sigma
from run_algo01_ds23_sample import read,sha,write
from leo.sky.frames import julian_day_from_utc_ns


def transition(a,b,c):
    target=c['collected_utc_ns']
    if not (a['collected_utc_ns']<=b['collected_utc_ns']<=target and
            a['epoch']<b['epoch']<c['epoch']<=target):return None
    gap=(b['epoch']-a['epoch'])/1e9
    if gap<1:return None
    jd,fr=julian_day_from_utc_ns(np.array([target]))
    states=[Satrec.twoline2rv(*v['lines']).sgp4(float(jd[0]),float(fr[0])) for v in (a,b,c)]
    if any(s[0] for s in states):return None
    pa,pb,pc=[np.asarray(s[1]) for s in states]
    velocity=np.asarray(states[1][2]);norm=float(velocity@velocity)
    old=float((pa-pb)@velocity/norm)
    innovation=float((pc-pb)@velocity/norm)
    age=(target-b['epoch'])/1e9
    prediction=-np.clip(age/gap,0,2)*old
    return dict(validation_time_ns=target,old_middle_alignment_s=old,
        next_innovation_s=innovation,unit_forecast_s=float(prediction),age_s=age,epoch_gap_s=gap,
        predicted_sigma_s=causal_phase_sigma(old,age,gap))


def select(rows):
    candidates=np.array([0.,.25,.5,.75,1.])
    if not rows:return dict(shrinkage=0.,scores=[0.]*5,candidates=candidates,transitions=0)
    target=np.array([r['next_innovation_s'] for r in rows])
    prediction=np.array([r['unit_forecast_s'] for r in rows])
    sigma=np.array([r['predicted_sigma_s'] for r in rows])
    limit=np.minimum(15.,3*sigma)
    scores=[float(np.sum(np.log1p(((target-np.clip(v*prediction,-limit,limit))/sigma)**2))) for v in candidates]
    chosen=int(np.argmin(scores))
    # Require an improvement above a one-parameter BIC-style log N cost.
    improvement=2*(scores[0]-scores[chosen])
    if improvement<=np.log(len(rows)):chosen=0
    return dict(shrinkage=float(candidates[chosen]),scores=scores,candidates=candidates,
                transitions=len(rows),robust_improvement=improvement,
                penalty_log_N=float(np.log(len(rows))),not_calibrated_probability_model=True)


def evaluate(rows,rho):
    if not rows:return dict(count=0)
    target=np.array([r['next_innovation_s'] for r in rows]);pred=np.array([r['unit_forecast_s'] for r in rows])
    sigma=np.array([r['predicted_sigma_s'] for r in rows]);limit=np.minimum(15.,3*sigma)
    error=target-np.clip(rho*pred,-limit,limit)
    return dict(count=len(rows),median_absolute_error_s=float(np.median(abs(error))),
                RMS_s=float(np.sqrt(np.mean(error**2))),median_abs_standardized_error=float(np.median(abs(error/sigma))),
                fraction_within_one_sigma=float(np.mean(abs(error)<sigma)))


def distribution_cost(errors,sigma,multiplier,nu):
    scale=np.asarray(sigma)*multiplier
    z=np.asarray(errors)/scale
    if nu is None:return np.log(2*np.pi)+2*np.log(scale)+z*z
    return (np.log((nu-2)*np.pi)+2*np.log(scale)+2*math.lgamma(nu/2)-
            2*math.lgamma((nu+1)/2)+(nu+1)*np.log1p(z*z/(nu-2)))


def select_distribution(rows):
    if len(rows)<30:return dict(shrinkage=0.,multiplier=1.,nu=None,fallback=True)
    target=np.array([r['next_innovation_s'] for r in rows]);pred=np.array([r['unit_forecast_s'] for r in rows])
    sigma=np.array([r['predicted_sigma_s'] for r in rows]);limit=np.minimum(15.,3*sigma)
    best=None
    for rho in (0.,.25,.5,.75,1.):
        error=target-np.clip(rho*pred,-limit,limit)
        for nu in (None,3.,4.,8.,16.):
            for multiplier in np.unique(np.r_[1.,np.geomspace(.1,4.,51)]):
                score=float(distribution_cost(error,sigma,multiplier,nu).sum())
                if best is None or score<best['cost']:
                    best=dict(shrinkage=rho,multiplier=float(multiplier),nu=nu,cost=score)
    baseline=float(distribution_cost(target,sigma,1.,None).sum())
    best.update(baseline_cost=baseline,transitions=len(rows),penalty=3*np.log(len(rows)),
                fallback=baseline-best['cost']<=3*np.log(len(rows)))
    if best['fallback']:best.update(shrinkage=0.,multiplier=1.,nu=None)
    return best


def evaluate_distribution(rows,parameters):
    if not rows:return dict(count=0)
    target=np.array([r['next_innovation_s'] for r in rows]);pred=np.array([r['unit_forecast_s'] for r in rows])
    sigma=np.array([r['predicted_sigma_s'] for r in rows]);limit=np.minimum(15.,3*sigma)
    error=target-np.clip(parameters['shrinkage']*pred,-limit,limit)
    return dict(count=len(rows),negative_twice_log_density=float(distribution_cost(
        error,sigma,parameters['multiplier'],parameters['nu']).sum()),
        median_absolute_error_s=float(np.median(abs(error))),
        standard_deviation_parameterization=True)


def run(path):
    history=read(path);cutoff=history['cutoff_utc_ns']
    rows=[]
    for number,versions in history['past_versions'].items():
        assert all(v['epoch']<=cutoff and v['collected_utc_ns']<=cutoff for v in versions)
        for k in range(2,len(versions)):
            row=transition(*versions[k-2:k+1])
            if row:rows.append(dict(norad=int(number),**row))
    times=sorted({r['validation_time_ns'] for r in rows})
    boundary=times[max(0,int(len(times)*.7)-1)] if times else cutoff
    training=[r for r in rows if r['validation_time_ns']<=boundary]
    validation=[r for r in rows if r['validation_time_ns']>boundary]
    prefix=select(training);full=select(rows)
    result=dict(case=history['case'],strictly_pre_RF=True,GPS_or_radio_used=False,
        history_sha256=sha(path),source_sha256=sha(Path(__file__)),temporal_split_boundary_ns=boundary,
        prefix_selection=prefix,all_past_selection=full,
        heldout_past_baseline=evaluate(validation,0),heldout_past_forecast=evaluate(validation,prefix['shrinkage']),
        all_past_baseline=evaluate(rows,0),all_past_forecast=evaluate(rows,full['shrinkage']),
        TLE_updates_are_proxies_not_orbit_truth=True,transitions=rows)
    prefix_distribution=select_distribution(training);all_distribution=select_distribution(rows)
    result.update(prefix_distribution=prefix_distribution,all_past_distribution=all_distribution,
        distribution_validation=evaluate_distribution(validation,prefix_distribution),
        original_distribution_validation=evaluate_distribution(validation,dict(shrinkage=0.,multiplier=1.,nu=None)))
    output=path.with_name(path.stem+'_forecast.json');write(output,result)
    print(history['case'],'transitions',len(rows),'prefix rho',prefix['shrinkage'],
          'all-past rho',full['shrinkage'],'heldout',result['heldout_past_forecast'],flush=True)
    print('TLE-only distribution',all_distribution,'past validation',result['distribution_validation'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('history',type=Path)
    run(parser.parse_args().history)
