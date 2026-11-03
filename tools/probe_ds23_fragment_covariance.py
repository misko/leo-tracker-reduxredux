"""Same-satellite/same-RF fragment offsets with matched marginal variance."""

import argparse
from pathlib import Path
import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem
from probe_ds23_learned_family_replacements import OUT as REPLACEMENTS
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_fragment_covariance'
CORRELATIONS=(0.,.5,.9)


def fragment_correlation(keys,rho):
    if not np.isfinite(rho) or not 0<=rho<1:raise ValueError('correlation in [0,1) required')
    matrix=np.eye(len(keys))
    for i,key in enumerate(keys):
        for j in range(i):
            if key==keys[j]:matrix[i,j]=matrix[j,i]=rho
    return matrix


def correlated_problem(scan,node,keep,arm,reference,powers,means,multiplier,nu,rho):
    p=make_problem(scan,node,keep,arm,reference,powers,means,multiplier,nu)
    keys=[(int(row['candidate_index']),float(scan.tracks[i]['rf_hz'])) for row,i in zip(p.rows,p.members,strict=True)]
    covariance=fragment_correlation(keys,rho);root=np.linalg.cholesky(covariance)
    p.constants=p.constants@root
    p.fragment_root=root
    return p


def refit_correlated(scan,node,keep,arm,powers,means,multiplier,nu,rho):
    reference=np.zeros(len(means));anchor=np.zeros(2);history=[]
    for epoch in range(5):
        p=correlated_problem(scan,node,keep,arm,reference,powers,means,multiplier,nu,rho)
        result=fit(p,anchor,iterations=48);anchor=np.array(result['parameters'])
        phase=p.state(anchor)['phases'][p.labels]
        history.append(dict(epoch=epoch,fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=np.clip(phase,-15,15)
    c=p.calculate(anchor);residual=p.residual(anchor)
    return dict(endpoint_east_north_km=anchor,endpoint_latlon=latlon(anchor),score=float(residual@residual),
        negative_twice_elbo=c['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        active_points=int(keep.sum()),gates=retained_metrics(p,anchor),history=history,state=p.state(anchor),
        phase_reference=reference,fragment_posterior_bias_hz=1000*p.fragment_root@c['coefficient'][-len(p.members):],
        fragment_correlation=p.fragment_root@p.fragment_root.T)


def pair_valid(pair):
    return all(t['compatible'] for arm in pair for t in pair[arm]['gates']['tracks'])


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    source=read(LEARNED/(case+'.json'));assert not source['GPS_used']
    selected=source['results']['mean_and_distribution'];keep=np.array(selected['mask'],bool)
    model=source['hyperparameters_from_pre_RF_TLE_only'];base=problem(scan,node,'c0',keep)
    _,receipts=phase_widths(scan,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    results={};OUT.mkdir(parents=True,exist_ok=True)
    for rho in CORRELATIONS:
        pair={arm:refit_correlated(scan,node,keep,arm,powers,means,model['multiplier'],model['nu'],rho) for arm in ('c0','fitted_c')}
        results[str(rho)]=dict(arms=pair,valid=pair_valid(pair))
        print(case,'rho',rho,'valid',pair_valid(pair),'ELBO',round(pair['c0']['negative_twice_elbo'],3),flush=True)
    assert results['0.0']['valid']
    chosen=min((str(r) for r in CORRELATIONS if results[str(r)]['valid']),
        key=lambda name:(results[name]['arms']['c0']['negative_twice_elbo'],float(name)))
    challenger=None;path=REPLACEMENTS/(case+'.json')
    if path.exists() and read(path)['best'] is not None:
        record=read(path);branch=changed_node(scan,node,record['best']['changes'])
        probe=problem(scan,branch,'c0',keep);_,r=phase_widths(scan,probe.labels)
        mu=forecast_phase_mean(r,model['shrinkage'])
        pair={arm:refit_correlated(scan,branch,keep,arm,powers,mu,model['multiplier'],model['nu'],float(chosen)) for arm in ('c0','fitted_c')}
        challenger=dict(arms=pair,valid=pair_valid(pair),changes=record['best']['changes'],
            delta_RF_loss=pair['c0']['negative_twice_elbo']-results[chosen]['arms']['c0']['negative_twice_elbo'])
    write(OUT/(case+'.json'),dict(case=case,results=results,chosen=chosen,challenger=challenger,
        fixed_mask=keep,GPS_used=False,source_sha256=sha(Path(__file__)),learned_input_sha256=sha(LEARNED/(case+'.json')),
        per_fragment_marginal_offset_sigma_hz=300.,same_family_and_exact_recorded_RF_groups_only=True,
        no_observation_trimming_or_identity_reselection_in_covariance_choice=True,
        paired_c_arms_have_same_data_labels_aliases_prior_and_budgets=True,
        selection='minimum normalized generalized c0 RF loss among paired-gate-passing covariance models',
        challenger_is_cached_RF_proposal_not_a_satellite_whitelist=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
