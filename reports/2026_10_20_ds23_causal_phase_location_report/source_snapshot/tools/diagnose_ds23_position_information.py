"""Local generalized position information after uncertain nuisance corrections."""

import argparse
from pathlib import Path
import numpy as np

from dsx01_joint_marginal import JointMarginal
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_position_information'


def marginal_information(derivative,features,weight,precision):
    d,u,w,p=map(lambda x:np.asarray(x,float),(derivative,features,weight,precision))
    if d.ndim!=2 or d.shape[1]!=2 or u.ndim!=2 or u.shape[0]!=len(d) or w.shape!=(len(d),) or p.shape!=(u.shape[1],):
        raise ValueError('matching two-coordinate derivatives, nuisance modes and precisions required')
    if not all(np.isfinite(x).all() for x in (d,u,w,p)) or np.any(w<=0) or np.any(p<=0):
        raise ValueError('finite modes and strictly positive precisions required')
    dw=d*np.sqrt(w)[:,None];uw=u*np.sqrt(w)[:,None]
    if u.shape[1]:
        rhs=uw.T@dw;gram=np.diag(p)+uw.T@uw
        root=np.linalg.cholesky(gram)
        solved=np.linalg.solve(root.T,np.linalg.solve(root,rhs))
        info=dw.T@(dw-uw@solved)
    else:info=dw.T@dw
    info=(info+info.T)/2;eigen,axes=np.linalg.eigh(info)
    if eigen[0]<=0:return dict(information=info,eigenvalues=eigen,positive_definite=False)
    covariance=np.linalg.inv(info)
    return dict(information=info,covariance_km2=covariance,eigenvalues=eigen,positive_definite=True,
        principal_sigma_km=1/np.sqrt(eigen),RMS_radius_km=float(np.sqrt(np.trace(covariance))),
        maximum_sigma_direction_east_north=axes[:,0])


def derivative_at(p,x,coefficient,step):
    def prediction(xy):
        c=JointMarginal.calculate(p,xy)
        return p.q*c['intercept']+c['features']@coefficient
    columns=[]
    for k in (0,1):
        delta=np.zeros(2);delta[k]=step
        columns.append((prediction(x+delta)-prediction(x-delta))/(2*step))
    return np.column_stack(columns)


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    source=read(LEARNED/(case+'.json'));assert not source['GPS_used']
    selected=source['results']['mean_and_distribution'];keep=np.array(selected['mask'],bool)
    model=source['hyperparameters_from_pre_RF_TLE_only'];base=problem(scan,node,'c0',keep)
    _,receipts=phase_widths(scan,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    results={}
    for arm in ('c0','fitted_c'):
        saved=selected['arms'][arm];reference=np.zeros(len(means))
        for h in saved['history']:
            p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
            x=np.array(h['fit']['parameters']);reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
        c=p.calculate(x);score=float(p.residual(x)@p.residual(x));assert abs(score-saved['score'])<1e-6
        d=derivative_at(p,x,c['coefficient'],.01)[keep]
        alternative=derivative_at(p,x,c['coefficient'],.02)[keep]
        weight=powers[p.noise_groups[keep]]*c['noise_precision'][p.noise_groups[keep]]/p.point_noise[keep]**2
        features=c['features'][keep];precision=c['coefficient_prior_precision']
        indices=np.arange(features.shape[1]);nb,ns=p.hardware.shape[1],p.smooth.shape[1]
        phase=nb+ns;orbit=phase+len(p.labels);constants=len(indices)-len(p.members)
        groups=dict(receiver_known=indices[phase:],phase_known=indices[(indices<phase)|(indices>=orbit)],
            orbits_known=indices[(indices<phase)|(indices>=constants)],fragment_known=indices[:constants],
            all_uncertain=indices,all_known=np.array([],int))
        controls={name:marginal_information(d,features[:,use],weight,precision[use]) for name,use in groups.items()}
        check=marginal_information(alternative,features,weight,precision)
        direct_noise_only=marginal_information(d,np.empty((len(d),0)),1/p.point_noise[keep]**2,np.empty(0))
        results[arm]=dict(controls=controls,step_0p02_check=check,direct_noise_only=direct_noise_only,
            endpoint_east_north_km=x,endpoint_latlon=saved['endpoint_latlon'],points=int(keep.sum()),
            score_replay_difference=score-saved['score'],phase_precision=c['coefficient_prior_precision'][phase:orbit],
            finite_difference_max_relative_change=float(np.linalg.norm(d-alternative)/max(np.linalg.norm(d),1e-30)))
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,GPS_used=False,source_sha256=sha(Path(__file__)),
        prior_input_sha256=sha(LEARNED/(case+'.json')),local_linearized_generalized_information_not_calibrated_CRLB=True,
        noise_and_student_prior_precisions_conditioned_at_fitted_endpoint=True,
        nuisance_freezing_controls_are_oracles_not_new_position_algorithms=True))
    print(case,{a:r['controls']['all_uncertain'].get('RMS_radius_km') for a,r in results.items()},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
