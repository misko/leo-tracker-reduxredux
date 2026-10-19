"""Fit positions with an externally qualified causal orbit-shape mean."""

import argparse
from pathlib import Path
import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,HISTORY,make_problem
from prototype_s01_causal_shape import previous_bank
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_causal_shape_ensemble'


def forecast_bank(current,previous,factors):
    factors=np.asarray(factors,float)
    if factors.shape!=(len(current['position_km']),) or not np.isfinite(factors).all():
        raise ValueError('one finite shape coefficient per satellite required')
    if not np.array_equal(current['time_s'],previous['time_s']):raise ValueError('common state time knots required')
    result=dict(time_s=np.array(current['time_s'],copy=True))
    for name in ('position_km','velocity_km_s'):
        result[name]=current[name]+factors[:,None,None]*(previous[name]-current[name])
    return result


def refit_shape(scan,node,keep,arm,powers,means,multiplier,nu,factors):
    reference=np.zeros(len(means));anchor=np.zeros(2);history=[]
    for epoch in range(5):
        p=make_problem(scan,node,keep,arm,reference,powers,means,multiplier,nu)
        old,_,_=previous_bank(scan,p.labels,previous_path=scan.previous_tle_path)
        p.sky=forecast_bank(p.sky,old,factors)
        result=fit(p,anchor,iterations=48);anchor=np.array(result['parameters'])
        phase=p.state(anchor)['phases'][p.labels]
        history.append(dict(epoch=epoch,fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=np.clip(phase,-15,15)
    c=p.calculate(anchor);residual=p.residual(anchor)
    return dict(endpoint_east_north_km=anchor,endpoint_latlon=latlon(anchor),score=float(residual@residual),
        negative_twice_elbo=c['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        active_points=int(keep.sum()),gates=retained_metrics(p,anchor),history=history,state=p.state(anchor),phase_reference=reference)


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    source=read(LEARNED/(case+'.json'));assert not source['GPS_used']
    primary=source['results']['mean_and_distribution'];keep=np.array(primary['mask'],bool)
    ensemble=read(HISTORY/(case+'_shape_ensemble.json'))
    assert ensemble['case']==case and ensemble['cutoff_utc_ns']==scan.receipt['cutoff_utc_ns']
    assert ensemble['strictly_pre_RF'] and not ensemble['GPS_or_radio_used']
    assert ensemble['shape_transition_sha256']==sha(HISTORY/(case+'_shape_forecast.json'))
    assert ensemble['history_sha256']==sha(HISTORY/(case+'.json'))
    model=source['hyperparameters_from_pre_RF_TLE_only'];base=problem(scan,node,'c0',keep)
    _,receipts=phase_widths(scan,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    chosen=ensemble['chosen'];factor=[]
    for r in receipts:
        ratio=np.clip((r['age_s']+150)/r['previous_epoch_gap_s'],0,2) if r['previous_epoch_gap_s'] else 0.
        factor.append(chosen['strength'] if chosen['mode']=='interpolate' else -chosen['strength']*ratio)
    factor=np.array(factor)
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    pair={arm:refit_shape(scan,node,keep,arm,powers,means,model['multiplier'],model['nu'],factor) for arm in ('c0','fitted_c')}
    valid=all(t['compatible'] for arm in pair for t in pair[arm]['gates']['tracks'])
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,arms=pair,valid=valid,policy_uses_baseline_fallback=not valid,
        fixed_mask=keep,shape_factors=factor,phase_label_norads=[int(scan.norads[j]) for j in base.labels],
        chosen_shape_model=chosen,causal_history_qualified=ensemble['qualified'],GPS_used=False,
        source_sha256=sha(Path(__file__)),ensemble_input_sha256=sha(HISTORY/(case+'_shape_ensemble.json')),
        signed_state_mean_is_the_only_model_change=True,
        original_state_uncertainty_modes_and_phase_priors_remain_unchanged=True,
        no_data_trimming_or_label_changes_in_this_control=True,paired_c_budgets_and_observations_match=True))
    print(case,'shape model',chosen['mode'],chosen['strength'],'valid',valid,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
