"""Phase prior calibrated on strictly pre-scan TLE innovations, not GPS or RF."""

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
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_receiver_smooth_prior import scale_posterior
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import OUT as SOURCE,ROOT,final_scan,read,sha,write

OUT=ROOT/'reports/2026_10_18_ds23_history_calibrated_phase'
HISTORY=ROOT/'reports/2026_10_18_ds23_causal_phase_mean/history'
ARMS=('c0','fitted_c')


def make_problem(scan,node,keep,arm,reference,weights,means,multiplier,nu,*,support_policy="nominal",extra_orbital_families=()):
    if support_policy not in ("nominal", "active", "active_uncertainty"):
        raise ValueError("unknown physical orbital support policy")
    p=problem(scan,node,arm,keep,reference)
    if support_policy == "active":
        from leo.analysis.research.orbital_support import restrict_to_active_orbital_support
        restrict_to_active_orbital_support(p)
    elif support_policy == "active_uncertainty":
        from leo.analysis.research.orbital_support import include_active_orbital_uncertainty
        from build_dsx01_orbit_modes import build_modes
        include_active_orbital_uncertainty(p,lambda supported:build_modes(scan,p.labels,supported,'physical'))
    if extra_orbital_families:
        from leo.analysis.research.orbital_support import include_active_orbital_uncertainty
        from build_dsx01_orbit_modes import build_modes
        include_active_orbital_uncertainty(p,lambda supported:build_modes(scan,p.labels,supported,'physical'),families=extra_orbital_families)
    p.phase_sigma*=multiplier
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if nu is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    def calculate(x):
        result=JointMarginal.calculate(p,x)
        features=result['features']
        scale=np.ones(width);scale[-len(p.members):]=.3
        raw=p.values-p.q*result['intercept']-features@mean
        present=np.unique(p.noise_groups[keep])
        bound=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=weights[present],prior_groups=None if nu is None else groups,prior_nu=4 if nu is None else nu)
        bound=scale_posterior(bound,scale)
        latent=bound['coefficient'].copy();bound['coefficient']=latent+mean;bound['latent_coefficient']=latent
        precision=np.zeros(len(p.members));precision[present]=bound['noise_precision'];bound['noise_precision']=precision
        bound['conditional_residual_hz']=p.values-p.q*result['intercept']-features@bound['coefficient']
        volume=float(2*np.sum(weights[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        bound['residual']=np.r_[bound['residual'],np.sqrt(volume)]
        result.update(bound)
        return result
    p.calculate=calculate
    return p


def refit(scan,node,keep,arm,weights,means,multiplier,nu):
    reference=np.zeros(len(means));anchor=np.zeros(2);history=[]
    for epoch in range(5):
        p=make_problem(scan,node,keep,arm,reference,weights,means,multiplier,nu)
        result=fit(p,anchor,iterations=48);anchor=np.array(result['parameters'])
        phase=p.state(anchor)['phases'][p.labels]
        history.append(dict(epoch=epoch,fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=np.clip(phase,-15,15)
    c=p.calculate(anchor);residual=p.residual(anchor)
    return dict(endpoint_east_north_km=anchor,endpoint_latlon=latlon(anchor),score=float(residual@residual),
        negative_twice_elbo=c['negative_twice_elbo'],normalization_constant=c['normalization_constant'],
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),active_points=int(keep.sum()),
        gates=retained_metrics(p,anchor),history=history,state=p.state(anchor),phase_reference=reference,
        phase_prior_mean_s=means,phase_prior_sigma_s=p.phase_sigma,
        phase_posterior_s=p.state(anchor)['phases'][p.labels],
        prior_penalty=float(np.sum(c['latent_coefficient']**2*c['coefficient_prior_precision'])),
        prior_precision=c['coefficient_prior_precision'],noise_precision=c['noise_precision'],
        precision_iterations=c['precision_iterations'],final_precision_change=c['final_log_precision_change'])


def run(case):
    OUT.mkdir(parents=True,exist_ok=True)
    scan=final_scan(case);original=read(SOURCE/case/'result.json')
    history=read(HISTORY/(case+'_forecast.json'))
    assert history['strictly_pre_RF'] and not history['GPS_or_radio_used']
    raw=read(HISTORY/(case+'.json'))
    assert history['case']==case and raw['case']==case
    assert history['history_sha256']==sha(HISTORY/(case+'.json'))
    assert raw['origin_utc_ns']==scan.receipt['origin_utc_ns']
    assert raw['cutoff_utc_ns']==scan.receipt['cutoff_utc_ns']
    assert all(v['epoch']<=raw['cutoff_utc_ns'] and v['collected_utc_ns']<=raw['cutoff_utc_ns']
               for versions in raw['past_versions'].values() for v in versions)
    learned=history['all_past_distribution']
    validation=history['distribution_validation'];unmodified=history['original_distribution_validation']
    qualified=validation['count']>=30 and validation['negative_twice_log_density']<unmodified['negative_twice_log_density']
    if not qualified:learned=dict(shrinkage=0.,multiplier=1.,nu=None,fallback=True)
    node,original_keep=original['final_node'],np.array(original['final_mask'],bool)
    base=problem(scan,node,'c0',original_keep)
    _,receipt=phase_widths(scan,base.labels)
    rho,multiplier,nu=learned['shrinkage'],learned['multiplier'],learned['nu']
    means=forecast_phase_mean(receipt,rho)
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    controls={'baseline':(means*0,1.,None),'mean_only':(means,1.,None),
              'distribution_only':(means*0,multiplier,nu),'mean_and_distribution':(means,multiplier,nu)}
    results={}
    for name,(mu,scale,tail) in controls.items():
        keep=original_keep.copy();steps=[]
        for epoch in range(4):
            pair={arm:refit(scan,node,keep,arm,weights,mu,scale,tail) for arm in ARMS}
            failed={r['component'] for arm in ARMS for r in pair[arm]['gates']['tracks'] if not r['compatible']}
            steps.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
            if not failed or epoch==3:break
            for row,sl in zip(base.rows,base.slices,strict=True):
                if row['component'] in failed:keep[sl]=False
        results[name]=dict(arms=pair,history=steps,mask=keep,valid=not failed)
        print(case,name,'points',int(keep.sum()),'valid',not failed,flush=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,hyperparameters_from_pre_RF_TLE_only=learned,
        earlier_TLE_validation_qualified=qualified,
        learned_on_all_causal_candidates_not_RF_selected_family_list=True,GPS_used=False,
        phase_tails_only_physical_orbit_modes_remain_Gaussian=True,paired_c_masks_labels_and_budgets=True,
        source_sha256=sha(Path(__file__)),history_forecast_sha256=sha(HISTORY/(case+'_forecast.json')),
        warning='raw RF score normalizing constants differ between Gaussian and Student priors; use full ELBO for comparisons'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
