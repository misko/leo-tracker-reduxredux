"""Physical RF-scaled covariance for same-family fragment constants."""

import argparse
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_family_catalogue import OUT,context
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha


def cross_rf_correlation(labels,rf,rho):
    labels,rf=np.asarray(labels),np.asarray(rf,float)
    if labels.ndim!=1 or rf.shape!=labels.shape or not np.isfinite(rf).all() or np.any(rf<=0) or not np.isfinite(rho) or not 0<=rho<1:
        raise ValueError('matching positive RF and correlation in [0,1) required')
    matrix=np.eye(len(labels))
    for label in np.unique(labels):
        ix=np.flatnonzero(labels==label);q=rf[ix]/max(rf[ix]);block=rho*np.outer(q,q)
        np.fill_diagonal(block,1.);matrix[np.ix_(ix,ix)]=block
    return matrix


def refit(scan,node,keep,powers,noise,model,arm,rho):
    base=problem(scan,node,arm,keep);_,receipts=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipts,model['shrinkage']);reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=eccentric_problem(scan,node,keep,arm,reference,powers,means,model,noise)
        covariance=cross_rf_correlation([r['candidate_index'] for r in p.rows],[scan.tracks[i]['rf_hz'] for i in p.members],rho)
        root=np.linalg.cholesky(covariance);p.constants=p.constants@root
        r=fit(p,x,iterations=48);x=np.array(r['parameters']);history.append(r)
        reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
    c=p.calculate(x);tracks=[]
    for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
        active=keep[sl]
        if not active.any():continue
        tracks.append(dict(track=scan.tracks[i]['key'],norad=row['candidate_norad'],time_s=scan.tracks[i]['times'][active],
            sigma_hz=p.point_noise[sl][active],conditional_residual_hz=c['conditional_residual_hz'][sl][active],
            noise_precision=float(c['noise_precision'][k])))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,state=p.state(x),
        negative_twice_elbo=c['negative_twice_elbo'],active_points=int(keep.sum()),phase_reference=reference,
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),gates=retained_metrics(p,x),tracks=tracks,
        fragment_correlation=covariance,fragment_posterior_bias_hz=1000*root@c['coefficient'][-len(p.members):])


def run(case):
    scan,node,keep,powers,noise,radio,model,old,offsets=context(case,True)
    catalogue=read(OUT/(case+'_companion.json'))
    pool=sorted([r for r in catalogue['trials'] if r.get('paired_valid')],key=lambda r:r['arms']['c0']['negative_twice_elbo'])[:3]
    original=next(r for r in catalogue['trials'] if r['proposal']['norad']==catalogue['source_norad'])
    if not any(r is original for r in pool):pool.append(original)
    trials=[]
    for selected in pool:
        candidate=changed_node(scan,node,selected['proposal']['changes'])
        arms={arm:refit(scan,candidate,keep,powers,noise,model,arm,.9) for arm in ('c0','fitted_c')}
        valid=all(t['compatible'] for a in arms.values() for t in a['gates']['tracks'])
        trials.append(dict(proposal=selected['proposal'],arms=arms,paired_valid=valid,independent_reference=selected['arms']))
        write(OUT/(case+'_cross_rf_partial.json'),dict(case=case,trials=trials))
        print(case,'cross RF',selected['proposal']['norad'],'valid',valid,flush=True)
    valid=[r for r in trials if r['paired_valid']]
    chosen=min(valid,key=lambda r:r['arms']['c0']['negative_twice_elbo']) if valid else None
    write(OUT/(case+'_cross_rf.json'),dict(case=case,trials=trials,chosen=chosen,correlation=.9,mask=keep,
        GPS_used=False,paired_c=True,per_fragment_marginal_sigma_300Hz_preserved=True,
        correlation_shared_across_RF_bands_and_receivers_for_same_candidate=True,
        source_sha256=sha(Path(__file__)),catalogue_input_sha256=sha(OUT/(case+'_companion.json')),
        fixed_observations_other_priors_and_budgets=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);run(parser.parse_args().case)
