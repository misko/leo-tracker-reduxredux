"""Rao-Blackwell importance audit of the existing Gaussian/Gamma RF evidence."""

import argparse
import math
from pathlib import Path
import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem
from probe_ds23_learned_family_replacements import OUT as REPLACEMENTS
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_marginal_evidence'


def gaussian_integral(y,u,sigma,groups,powers,tau,precision):
    """Exact conditional -2 log generalized evidence, integrating Gaussian modes."""
    y,u,sigma=np.asarray(y),np.asarray(u),np.asarray(sigma)
    w=powers[groups]*tau[groups]/sigma**2
    gram=np.diag(precision)+u.T@(w[:,None]*u)
    root=np.linalg.cholesky(gram)
    rhs=u.T@(w*y);a=np.linalg.solve(root.T,np.linalg.solve(root,rhs))
    innovation=y-u@a
    quadratic=float(np.sum(w*innovation**2)+np.sum(precision*a*a))
    volume=float(2*np.log(np.diag(root)).sum()-np.log(precision).sum())
    constant=float(np.sum(powers[groups]*(np.log(2*np.pi)+2*np.log(sigma)-np.log(tau[groups]))))
    return quadratic+volume+constant


def gamma_logratio(draw,prior_shape,prior_rate,shape,rate):
    lgamma=np.vectorize(math.lgamma,otypes=[float])
    constant=prior_shape*np.log(prior_rate)-math.lgamma(prior_shape)-shape*np.log(rate)+lgamma(shape)
    return np.sum(constant+(prior_shape-shape)*np.log(draw)-(prior_rate-rate)*draw,axis=1)


def integrate(y,u,sigma,groups,powers,noise_mean,phase_indices,phase_mean,nu,*,samples=1024,seed=231019):
    rng=np.random.default_rng(seed);counts=np.bincount(groups,minlength=len(powers))
    noise_shape=2+powers*counts/2;noise_rate=noise_shape/noise_mean
    tau=rng.gamma(noise_shape,1.,size=(samples,len(powers)))/noise_rate
    logratio=gamma_logratio(tau,2.,2.,noise_shape,noise_rate)
    if len(phase_indices):
        shape=np.full(len(phase_indices),(nu+1)/2);rate=shape/phase_mean
        phase=rng.gamma(shape,1.,size=(samples,len(shape)))/rate
        logratio+=gamma_logratio(phase,nu/2,(nu-2)/2,shape,rate)
    else:phase=np.empty((samples,0))
    logweight=np.empty(samples)
    for k in range(samples):
        precision=np.ones(u.shape[1]);precision[phase_indices]=phase[k]
        logweight[k]=-.5*gaussian_integral(y,u,sigma,groups,powers,tau[k],precision)+logratio[k]
    maximum=float(logweight.max());mass=np.exp(logweight-maximum)
    estimate=-2*(maximum+np.log(mass.mean()));ess=float(mass.sum()**2/(mass@mass))
    se=float(2*np.std(mass,ddof=1)/np.sqrt(samples)/mass.mean())
    maxweight=float(mass.max()/mass.sum())
    return dict(negative_twice_log_evidence=float(estimate),Monte_Carlo_SE=se,effective_samples=ess,
        samples=samples,maximum_normalized_weight=maxweight,log_importance_weights=logweight,
        reliable_by_declared_ESS_rule=ess>=max(50,.1*samples) and maxweight<.05)


def run(case,samples):
    scan=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    source=read(LEARNED/(case+'.json'));assert not source['GPS_used']
    model=source['hyperparameters_from_pre_RF_TLE_only'];primary=source['results']['mean_and_distribution']
    keep=np.array(primary['mask'],bool)
    replacement=read(REPLACEMENTS/(case+'.json'))
    assert replacement['best'] is not None and np.array_equal(keep,replacement['fixed_mask'])
    alternative=changed_node(scan,node,replacement['best']['changes'])
    candidates=[('incumbent',node,primary['arms']['c0']),
        ('challenger',alternative,replacement['best_paired_finalists']['c0'])]
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    results={}
    for name,branch,saved in candidates:
        base=problem(scan,branch,'c0',keep);_,receipts=phase_widths(scan,base.labels)
        means=forecast_phase_mean(receipts,model['shrinkage']);reference=np.zeros(len(means))
        for h in saved['history']:
            p=make_problem(scan,branch,keep,'c0',reference,powers,means,model['multiplier'],model['nu'])
            x=np.array(h['fit']['parameters']);reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
        c=p.calculate(x);assert abs(float(p.residual(x)@p.residual(x))-saved['score'])<1e-6
        features=c['features'].copy();start=p.hardware.shape[1]+p.smooth.shape[1]
        mean=np.zeros(features.shape[1]);mean[start:start+len(means)]=means/p.phase_sigma
        raw=p.values-p.q*c['intercept']-features@mean
        features[:,-len(p.members):]*=.3
        present,groups=np.unique(p.noise_groups[keep],return_inverse=True)
        phase_indices=np.arange(start,start+len(means)) if model['nu'] is not None else np.array([],int)
        result=integrate(raw[keep],features[keep],p.point_noise[keep],groups,powers[present],
            c['noise_precision'][present],phase_indices,c['coefficient_prior_precision'][phase_indices],model['nu'],samples=samples)
        result.update(variational_negative_twice_ELBO=c['negative_twice_elbo'],
            estimated_variational_gap=c['negative_twice_elbo']-result['negative_twice_log_evidence'],
            endpoint_east_north_km=x,seed=231019)
        results[name]=result
        print(case,name,{k:v for k,v in result.items() if k not in ['log_importance_weights','endpoint_east_north_km']},flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,GPS_used=False,source_sha256=sha(Path(__file__)),
        no_position_refit=True,no_prior_model_change=True,physical_CFO_data_labels_and_weights_match_frozen_candidate_trials=True,
        c0_only_objective_audit_not_a_paired_localization_algorithm_comparison=True,
        estimate_not_qualified_if_ESS_rule_fails=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    parser.add_argument('--samples',type=int,default=1024);args=parser.parse_args();run(args.case,args.samples)
