"""Past-TLE-only signed phase-forecast means; no future elements or GPS."""

import argparse
from pathlib import Path

import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_receiver_smooth_prior import scale_posterior
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import OUT as SOURCE,ROOT,read,write,sha,final_scan

OUT=ROOT/"reports/2026_10_18_ds23_causal_phase_mean"
ARMS=("c0","fitted_c")


def forecast_phase_mean(receipts,shrinkage):
    if not 0<=shrinkage<=1:raise ValueError("fixed shrinkage must lie in [0,1]")
    means=[]
    for r in receipts:
        delta,gap=r["old_new_alignment_s"],r["previous_epoch_gap_s"]
        value=0. if delta is None or gap is None or gap<1 else -shrinkage*np.clip((r['age_s']+150)/gap,0,2)*delta
        means.append(float(np.clip(value,-min(15,3*r['sigma_s']),min(15,3*r['sigma_s']))))
    return np.asarray(means)


def forecast_problem(scan,node,keep,arm,reference,weights,means):
    p=problem(scan,node,arm,keep,reference)
    prior=np.zeros(p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)+len(p.members))
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    prior[begin:begin+len(p.labels)]=means/p.phase_sigma
    def calculate(x):
        result=JointMarginal.calculate(p,x)
        features=result["features"]
        scale=np.ones(features.shape[1]);scale[-len(p.members):]=.3
        raw=p.values-p.q*result["intercept"]-features@prior
        present=np.unique(p.noise_groups[keep])
        bound=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],powers=weights[present])
        bound=scale_posterior(bound,scale)
        latent=bound['coefficient'].copy()
        bound['coefficient']=prior+latent
        bound['latent_coefficient']=latent
        precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
        bound['conditional_residual_hz']=p.values-p.q*result['intercept']-features@bound['coefficient']
        volume=float(2*np.sum(weights[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        result.update(bound)
        return result
    p.calculate=calculate
    return p


def refit(scan,node,keep,arm,weights,means):
    reference=np.zeros(len(means));anchor=np.zeros(2);history=[]
    for epoch in range(5):
        p=forecast_problem(scan,node,keep,arm,reference,weights,means)
        result=fit(p,anchor,iterations=48);anchor=np.asarray(result['parameters'])
        phase=p.state(anchor)['phases'][p.labels]
        history.append(dict(epoch=epoch,fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=np.clip(phase,-15,15)
    c=p.calculate(anchor)
    return dict(endpoint_east_north_km=anchor,endpoint_latlon=latlon(anchor),score=float(p.residual(anchor)@p.residual(anchor)),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        active_points=int(keep.sum()),gates=retained_metrics(p,anchor),history=history,state=p.state(anchor),
        phase_prior_mean_s=means,phase_reference=reference,phase_posterior_s=p.state(anchor)['phases'][p.labels],
        noise_precision=c['noise_precision'],prior_penalty=float(np.sum(c['latent_coefficient']**2*c['coefficient_prior_precision'])),
        nuisance_mean_does_not_use_RF_or_GPS=True)


def run(case):
    OUT.mkdir(parents=True,exist_ok=True)
    scan=final_scan(case);baseline=read(SOURCE/case/'result.json')
    node=baseline['final_node'];original=np.asarray(baseline['final_mask'],bool)
    base=problem(scan,node,'c0',original)
    _,receipts=phase_widths(scan,base.labels)
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    results={}
    for shrinkage in (0.,.5,1.):
        means=forecast_phase_mean(receipts,shrinkage);keep=original.copy();history=[]
        for epoch in range(4):
            pair={arm:refit(scan,node,keep,arm,weights,means) for arm in ARMS}
            failed={r['component'] for arm in ARMS for r in pair[arm]['gates']['tracks'] if not r['compatible']}
            history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
            if not failed or epoch==3:break
            for row,sl in zip(base.rows,base.slices,strict=True):
                if row['component'] in failed:keep[sl]=False
        results[str(shrinkage)]=dict(arms=pair,history=history,mask=keep,valid=not failed,means=means)
        print(case,'shrinkage',shrinkage,'points',int(keep.sum()),'valid',not failed,flush=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,causal_history_receipts=receipts,GPS_used=False,
        prediction_is_unvalidated_sensitivity_not_orbit_truth=True,latest_causal_TLE_is_nominal_mean=True,
        same_covariance_and_weights_between_shrinkages=True,matched_c_observations_masks_budget=True,
        source_sha256=sha(Path(__file__))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
