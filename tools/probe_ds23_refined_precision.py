"""Matched partial CFO/uncertainty interventions; GPS is absent from inference."""

import argparse
import copy
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_refined_noise import learn_noise
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_receiver_smooth_prior import scale_posterior
from probe_ds23_refined_curve_position import update_values
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_refined_precision'


def precision_problem(scan,node,keep,arm,reference,powers,means,model,by_id):
    p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
    original_noise=p.point_noise.copy()
    ids=[oid for i in p.members for oid in scan.tracks[i]['observation_ids']]
    p.point_noise=np.array([by_id.get(oid,sigma) for oid,sigma in zip(ids,original_noise,strict=True)])
    if not np.isfinite(p.point_noise).all() or np.any(p.point_noise<1):raise ValueError('finite noise >=1 Hz required')
    begin=p.hardware.shape[1]+p.smooth.shape[1];width=begin+len(p.labels)+3*len(p.supported)+len(p.members)
    mean=np.zeros(width);mean[begin:begin+len(p.labels)]=means/p.phase_sigma
    groups=np.full(width,-1,int)
    if model['nu'] is not None:groups[begin:begin+len(p.labels)]=np.arange(len(p.labels))
    def calculate(x):
        c=JointMarginal.calculate(p,x);features=c['features'];scale=np.ones(width);scale[-len(p.members):]=.3
        raw=p.values-p.q*c['intercept']-features@mean;present=np.unique(p.noise_groups[keep])
        b=hierarchical_bound(raw[keep],(features*scale)[keep],p.point_noise[keep],p.noise_groups[keep],
            powers=powers[present],prior_groups=None if model['nu'] is None else groups,
            prior_nu=4 if model['nu'] is None else model['nu'])
        b=scale_posterior(b,scale);b['latent_coefficient']=b['coefficient'].copy();b['coefficient']+=mean
        precision=np.zeros(len(p.members));precision[present]=b['noise_precision'];b['noise_precision']=precision
        b['conditional_residual_hz']=p.values-p.q*c['intercept']-features@b['coefficient']
        # A fixed 1 Hz reference makes the extra residual real for every arm.
        # The full ELBO already includes its absolute noise normalization.
        volume=float(2*np.sum(powers[p.noise_groups[keep]]*np.log(p.point_noise[keep])))
        b['residual']=np.r_[b['residual'],np.sqrt(volume)];c.update(b)
        return c
    p.calculate=calculate;p.original_point_noise=original_noise
    p.refined_noise_ids=ids
    return p


def refit(scan,node,keep,arm,powers,means,model,by_id):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=precision_problem(scan,node,keep,arm,reference,powers,means,model,by_id)
        r=fit(p,x,iterations=48);x=np.array(r['parameters']);history.append(r)
        reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
    c=p.calculate(x);tracks=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        active=keep[sl]
        if not active.any():continue
        ids=np.array(p.refined_noise_ids[sl]);sigma=p.point_noise[sl][active]
        k=p.members.index(i);precision=c['noise_precision'][k]
        r=c['conditional_residual_hz'][sl][active]
        tracks.append(dict(track=scan.tracks[i]['key'],receiver=scan.tracks[i]['receiver'],channel=scan.tracks[i]['channel'],
            norad=row['candidate_norad'],points=int(active.sum()),
            refined_points=sum(o in by_id for o in ids[active]),nominal_noise_hz=sigma,
            noise_precision=precision,effective_noise_hz=sigma/np.sqrt(precision),
            conditional_residual_hz=r,RMS_hz=float(np.sqrt(np.mean(r*r)))))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,state=p.state(x),
        negative_twice_elbo=c['negative_twice_elbo'],score=float(p.residual(x)@p.residual(x)),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),active_points=int(keep.sum()),
        gates=retained_metrics(p,x),phase_reference=reference,tracks=tracks)


def run(case):
    OUT.mkdir(parents=True,exist_ok=True);raw=read(RAW/(case+'_tracks.json'))
    learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution']
    keep=np.array(primary['mask'],bool);node=read(SOURCE/case/'result.json')['final_node']
    model=learned['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    scan=final_scan(case);base=problem(scan,node,'c0',keep)
    _,receipts=phase_widths(scan,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    by_id,radio=learn_noise(raw);modified=copy.deepcopy(scan);updates=update_values(modified,raw['rows'],'joint_CFO_epoch_rate')
    results={}
    controls={'original_reference1':(scan,{}),'refined_sigma40':(modified,{o:max(40,v) for o,v in by_id.items()}),
              'refined_predictive_sigma':(modified,by_id)}
    for name,(s,noise) in controls.items():
        pair={arm:refit(s,node,keep,arm,powers,means,model,noise) for arm in ('c0','fitted_c')}
        valid=all(t['compatible'] for a in pair.values() for t in a['gates']['tracks'])
        results[name]=dict(trial_arms=pair,paired_valid=valid,reported_arms=pair if valid else primary['arms'])
        write(OUT/(case+'_partial.json'),dict(case=case,results=results))
        print(case,name,'paired valid',valid,flush=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,incumbent_arms=primary['arms'],
        radio_noise_receipts=radio,proposed_noise_by_id=by_id,CFO_updates=updates,
        mask_labels_aliases_other_priors_and_budgets_preserved=True,paired_c=True,
        refined_noise_is_RF_only_predictive_proxy_not_calibrated_error_bar=True,
        nuisance_constants_and_Gamma_noise_prior_unchanged=True,all_residuals_use_reference1Hz=True,
        raw_sha256=sha(RAW/(case+'_tracks.json')),source_sha256=sha(Path(__file__)),
        radio_noise_source_sha256=sha(ROOT/'tools/ds23_refined_noise.py'),GPS_used=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
