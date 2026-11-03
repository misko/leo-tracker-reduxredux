"""Small shared satellite carrier-frequency rates under the causal DS23 prior."""

import argparse
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_shared_rate'


def rate_design(labels,q,times,families,sigma):
    labels,q,t=map(np.asarray,(labels,q,times))
    if labels.ndim!=1 or labels.shape!=q.shape or labels.shape!=t.shape or not np.isfinite(q).all() or not np.isfinite(t).all() or not np.isfinite(sigma) or sigma<0:
        raise ValueError('matching finite times and RF scales; nonnegative rate width required')
    return np.column_stack([(labels==j)*q*sigma*(t-150) for j in families]) if families and sigma else np.empty((len(t),0))


def rate_problem(scan,node,keep,arm,reference,powers,means,model,sigma):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    if sigma==0:return p
    families=[]
    for j in p.labels:
        receivers={scan.tracks[i]['receiver'] for row,i,sl in zip(p.rows,p.members,p.slices,strict=True) if row['candidate_index']==j and keep[sl].any()}
        if receivers=={1,2}:families.append(j)
    local=[p.labels.index(j) for j in families]
    rates=rate_design(p.flat_labels,p.q,p.flat_times,local,sigma);nr=rates.shape[1]
    if not nr:return p
    begin=p.hardware.shape[1]+p.smooth.shape[1];width=begin+len(p.labels)+3*len(p.supported)+nr+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model['nu'] is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    def calculate(x):
        c=JointMarginal.calculate(p,x);old=c['features'];stop=old.shape[1]-len(p.members)
        features=np.column_stack((old[:,:stop],rates,old[:,stop:]));scale=np.ones(width);scale[-len(p.members):]=.3
        raw=p.values-p.q*c['intercept']-features@mean;present=np.unique(p.noise_groups[keep])
        b=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=None if model['nu'] is None else groups,prior_nu=4 if model['nu'] is None else model['nu'])
        b=scale_posterior(b,scale);b['latent_coefficient']=b['coefficient'].copy();b['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=b['noise_precision'];b['noise_precision']=precision
        b['conditional_residual_hz']=p.values-p.q*c['intercept']-features@b['coefficient']
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep]/40)))
        b['residual']=np.r_[b['residual'],np.sqrt(volume)];c.update(b,features=features)
        return c
    p.calculate=calculate
    original_state=p.state
    def state(x):
        s=original_state(x);c=p.calculate(x);stop=c['features'].shape[1]-len(p.members)
        s['satellite_frequency_rates_hz_s']={str(int(scan.norads[j])):float(a*sigma) for j,a in zip(families,c['coefficient'][stop-nr:stop],strict=True)}
        return s
    def conditional_frequency(x):
        c=p.calculate(x);stop=c['features'].shape[1]-len(p.members)
        return c['intercept']+c['features'][:,begin:stop]@c['coefficient'][begin:stop]/p.q,c['elevation']
    p.state=state;p.conditional_frequency=conditional_frequency
    p.shared_rate_count=nr;p.shared_rate_families=families
    return p


def refit(scan,node,keep,arm,powers,means,model,sigma):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=rate_problem(scan,node,keep,arm,reference,powers,means,model,sigma)
        fitted=fit(p,x,iterations=48);x=np.array(fitted['parameters']);history.append(fitted)
        reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
    c=p.calculate(x)
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,state=p.state(x),
        negative_twice_elbo=c['negative_twice_elbo'],score=float(p.residual(x)@p.residual(x)),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),active_points=int(keep.sum()),
        gates=retained_metrics(p,x),phase_reference=reference,rate_count=getattr(p,'shared_rate_count',0))


def run(case):
    scan=final_scan(case);node=read(SOURCE/case/'result.json')['final_node'];learned=read(LEARNED/(case+'.json'))
    primary=learned['results']['mean_and_distribution'];keep=np.array(primary['mask'],bool)
    model=learned['hyperparameters_from_pre_RF_TLE_only'];powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    p=rate_problem(scan,node,keep,'c0',np.zeros(len({r['candidate_index'] for r in node['seed']['rows']})),powers,np.zeros(len({r['candidate_index'] for r in node['seed']['rows']})),model,0)
    _,receipts=phase_widths(scan,p.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    results={'0.0':dict(arms=primary['arms'],paired_valid=True)};OUT.mkdir(parents=True,exist_ok=True)
    for sigma in (.25,1.):
        pair={arm:refit(scan,node,keep,arm,powers,means,model,sigma) for arm in ('c0','fitted_c')}
        valid=all(t['compatible'] for r in pair.values() for t in r['gates']['tracks'])
        results[str(sigma)]=dict(arms=pair,paired_valid=valid)
        write(OUT/(case+'_partial.json'),dict(case=case,results=results,source_sha256=sha(Path(__file__))))
        print(case,'sigma',sigma,'paired valid',valid,flush=True)
    chosen=min([k for k,v in results.items() if v['paired_valid']],key=lambda k:results[k]['arms']['c0']['negative_twice_elbo'])
    write(OUT/(case+'.json'),dict(case=case,results=results,chosen=chosen,arms=results[chosen]['arms'],fixed_mask=keep,powers=powers,
        source_sha256=sha(Path(__file__)),learned_input_sha256=sha(LEARNED/(case+'.json')),GPS_used=False,
        unchanged_data_aliases_identities_and_other_priors=True,paired_c_budgets_and_data_match=True,
        only_families_with_active_curved_support_on_both_receivers_receive_rates=True,
        rate_widths_are_engineering_hypotheses_not_claimed_calibrated_clock_priors=True,
        mode_selection_uses_normalized_c0_ELBO_and_both_arm_gates=True))
    print(case,'chosen',chosen,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
