"""Pilot failure decomposition and whole-family calibration deletion checks."""

import argparse
from pathlib import Path
import time

import numpy as np
from scipy.linalg import cho_solve
from scipy.stats import chi2

import debug_fast_graph_unassociated as report
from benchmark_graph_covariance import refit
from correlated_curve_prediction import gaussian,randomized_blocks
from probe_graph_shared_high_channels import context,select_targets
from probe_high_channel_correlated_noise import (prediction_geometry,noise_diagnostics,
    calibrate,validation)


def gls_mean(residual,covariance,design):
    root=np.linalg.cholesky(covariance)
    inv_design=cho_solve((root,True),design)
    info=design.T@inv_design
    coefficient=np.linalg.solve(info,inv_design.T@residual)
    uncertainty=np.sqrt(np.diag(np.linalg.inv(info)))
    return dict(mean_hz=coefficient,sigma_hz=uncertainty,z=coefficient/uncertainty)


def failure(d,parent):
    extras=report.read(parent/'target_entries.json')
    model=report.read(parent/'calibration.json')['best_correlated'];result={}
    for arm,(p,x) in d['problems'].items():
        evaluate,view,_,order,_=prediction_geometry(p,[],d['powers'],extras,model)
        _,raw,cov,_=evaluate(x);times=view.flat_times
        train,split=randomized_blocks(times,seed=1)
        owner=np.repeat(np.arange(len(extras)),[e['points'] for e in extras])[order]
        raw,cov,times,train=raw[order],cov[np.ix_(order,order)],times[order],train[order]
        root=np.linalg.cholesky(cov[np.ix_(train,train)]);cross=cov[np.ix_(~train,train)]
        prediction=cross@cho_solve((root,True),raw[train]);r=raw[~train]-prediction
        post=cov[np.ix_(~train,~train)]-cross@cho_solve((root,True),cross.T);post=(post+post.T)/2
        tt=times[~train];owners=owner[~train];chronological=gaussian(r,post);reverse=gaussian(r[::-1],post[::-1,::-1])
        by_track={}
        for k,e in enumerate(extras):
            use=owners==k
            marginal=gaussian(r[use],post[np.ix_(use,use)])
            by_track[e['component']]=dict(
                chronological=noise_diagnostics(chronological['whitened'][use],tt[use]),
                reverse_factorization=noise_diagnostics(reverse['whitened'][::-1][use],tt[use]),
                marginal=noise_diagnostics(marginal['whitened'],tt[use]),
                marginal_mean=gls_mean(r[use],post[np.ix_(use,use)],np.ones((use.sum(),1))))
        result[arm]=dict(split=split,times_s=tt,owner=owners,residual_hz=r,
            conditional_sigma_hz=np.sqrt(np.diag(post)),per_track=by_track,
            common_and_differential_mean=gls_mean(r,post,np.column_stack((np.ones(len(r)),np.where(owners==0,1.,-1.)))),
            chronological_objective=chronological['objective'],reverse_objective=reverse['objective'],
            joint_chi2=chronological['quadratic'],joint_degrees_of_freedom=len(r),
            joint_chi2_upper_tail_probability=float(chi2.sf(chronological['quadratic'],len(r))))
    return result


def family(d,parent,norad):
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    began=time.monotonic();p,_=d['problems']['c0'];scan=d['scan'];keep=d['keep'].copy();extras=[]
    for k,(r,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        if r['candidate_norad']!=norad:continue
        t=scan.tracks[i]
        if d['keep'][sl].all() and t['receiver']==1 and len(t['times'])>=12 and np.ptp(t['times'])>=24:
            extras.append(dict(track_index=i,component=t['key'],candidate_index=r['candidate_index'],norad=norad,
                alias=int(p.alias[k]),points=len(t['times']),observation_ids=t['observation_ids']))
        keep[sl]=False
    if not extras:return dict(norad=norad,status='no_eligible_complete_RX1_curve')
    entries=[e for e in d['entries'] if e['norad']!=norad]
    # Restore the strictly pre-RF causal phase forecasts; do not carry the
    # incumbent RF-selected signed phase means into this deletion experiment.
    _,receipts=phase_widths(scan,p.labels)
    means=forecast_phase_mean(receipts,d['model']['shrinkage'])
    pair,problems=refit(d,keep,policy='nominal',entries=entries,means=np.asarray(means))
    fold=dict(d,keep=keep,entries=entries,means=np.asarray(means),problems=problems)
    targets=select_targets(d)
    calibration=calibrate(fold,targets,sorted({57701,58101,norad}))
    predictions={name:validation(fold,extras,model) for name,model in
        (('white',calibration['null']),('correlated',calibration['best_correlated']))}
    record=dict(norad=norad,status='complete',removed_curved_points=int(d['keep'].sum()-keep.sum()),
        removed_predictive_points=sum(e['points'] for e in d['entries'] if e['norad']==norad),
        held_RX1_points=sum(e['points'] for e in extras),held_entries=extras,
        training_fold=pair,calibration=calibration,predictions=predictions,
        seconds=time.monotonic()-began,all_family_observations_excluded_from_calibration=True,
        prior_phase_means='strictly pre-RF causal forecasts; signed RF choices removed',
        orbit_uncertainty='nominal physical prior retained for withheld family, not falsely zero uncertainty',
        caveat='Identities, graph, aliases and incumbent likelihood powers are fixed; not blind acquisition/identity validation')
    print('Family',norad,[(a,predictions['white'][a]['joint']['objective']-predictions['correlated'][a]['joint']['objective'],
        predictions['correlated'][a]['joint']['noise']['noise_screen_pass']) for a in ('c0','fitted_c')],flush=True)
    return record


def main(args):
    args.output.mkdir(parents=True,exist_ok=False);d=context(args)
    if args.mode=='failure':report.write(args.output/'failure.json',failure(d,args.parent))
    else:report.write(args.output/'family.json',family(d,args.parent,args.norad))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('failure','family'))
    for name in ('run','ch1','source-root','parent','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--norad',type=int);main(p.parse_args())
