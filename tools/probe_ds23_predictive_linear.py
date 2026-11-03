"""Linear extension position evidence with calibration learned from curved data only."""

import argparse
import time
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_predictive_linear import attach_predictive_linear
from evaluate_ds23_phase_refreshed import extend_associations
from investigate_dsx01_localization_failures import fit
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import make_problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,write,sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile

OUT=ROOT/'reports/2026_10_19_ds23_predictive_linear'


def select_entries(p,x,original_metrics):
    extra=extend_associations(p,x,original_metrics);lookup={t['key']:i for i,t in enumerate(p.scan.tracks)}
    original_ids={o for r in original_metrics['tracks'] for o in r['observation_ids']}
    owners={j:{p.scan.tracks[i]['receiver'] for i,row,sl in zip(p.members,p.rows,p.slices,strict=True)
        if row['candidate_index']==j and p.keep[sl].any()} for j in p.labels}
    selected=[];seen=set(original_ids)
    for r in extra['tracks']:
        i=lookup[r['component']];t=p.scan.tracks[i]
        if r['association_source']!='frozen_calibration_extension' or i in p.scan.curved or len(t['times'])<6:continue
        ids=set(t['observation_ids'])
        if ids&seen:continue
        # Existing extension uses the exact physical phase; recover its integer
        # alias against the archived CFO and frozen mean receiver calibration.
        # build a zero-alias prediction through the same physical feature builder
        e=dict(track_index=i,component=t['key'],candidate_index=r['candidate_index'],norad=r['norad'],alias=0,
            points=len(t['times']),cross_receiver_curved_support=len(owners[r['candidate_index']])==2,
            observation_ids=t['observation_ids'])
        from ds23_predictive_linear import linear_geometry
        from ds23_height_problem import geometry_features
        from leo.analysis.research.retained_track_likelihood import PERIOD
        view,values,_,_,_=linear_geometry(p,[e]);g=geometry_features(view,x,0.)
        mean=view.q*g['intercept']+g['features']@p.calculate(x)['coefficient']
        e['alias']=int(np.rint(-np.mean(values-mean)/PERIOD))
        selected.append(e);seen|=ids
    return selected


def refit(scan,node,keep,powers,means,model,arm,entries):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
        attach_predictive_linear(p,entries,powers)
        r=fit(p,x,iterations=48);x=np.array(r['parameters']);next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=r,phase_change_s=float(max(abs(next_phase-reference)))))
        reference=next_phase
    c=p.calculate(x);curved=p.curved_calculate(x) if entries else c
    linear_gates=[]
    for e,sl in zip(entries,getattr(p,'linear_slices',[]),strict=True):
        t=scan.tracks[e['track_index']];residual=c['linear_raw_prediction_residual_hz'][sl]
        terms=profile(residual,np.zeros(len(residual)),*scan.white[e['track_index']],bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],t['times'])
        valid=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0
            and noise['noise_screen_pass'][0] and min(c['linear_elevation'][sl])>=0)
        linear_gates.append(dict(component=e['component'],compatible=valid,points=e['points'],
            rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),observation_ids=e['observation_ids']))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,phase_reference=p.reference,
        state=p.state(x),gates=retained_metrics(p,x),linear_gates=linear_gates,
        active_points=int(keep.sum()),additional_predictive_points=sum(e['points'] for e in entries),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        negative_twice_elbo=c['negative_twice_elbo'],curved_negative_twice_elbo=curved['negative_twice_elbo'],
        linear_predictive_objective=c.get('linear_predictive_objective',0.),
        calibration_replay_max_coefficient_difference=float(max(abs(c['coefficient']-curved['coefficient']))),
        final_phase_change_s=history[-1]['phase_change_s'])


def run(case):
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/(case+'.json')).exists():raise FileExistsError('preserve scientific outputs')
    scan,node,keep,powers,means,model,_,baseline=context(case,'archived')
    b=baseline['c0'];p=make_problem(scan,node,keep,'c0',np.array(b['phase_reference']),powers,means,model['multiplier'],model['nu'])
    x=np.array(b['endpoint_east_north_km']);entries=select_entries(p,x,retained_metrics(p,x));results={}
    for method,chosen in [('all_linear',entries),('cross_rx_linear',[e for e in entries if e['cross_receiver_curved_support']])]:
        pair={arm:refit(scan,node,keep,powers,means,model,arm,chosen) for arm in ('c0','fitted_c')}
        valid=all(all(t['compatible'] for t in r['gates']['tracks']+r['linear_gates']) and r['final_phase_change_s']<=.01 for r in pair.values())
        results[method]=dict(arms=pair,entries=chosen,paired_valid=valid,policy_arms=pair if valid else baseline)
        write(OUT/(case+'_partial.json'),dict(case=case,results=results))
        print(case,method,'curves',len(chosen),'points',sum(e['points'] for e in chosen),'paired valid',valid,flush=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,baseline_arms=baseline,mask=keep,powers=powers,
        no_GPS_used=True,no_IQ_reread=True,no_original_point_trimming=True,
        curved_only_calibration_no_linear_normal_equation_update=True,
        shared_full_calibration_covariance_preserved=True,unseen_Gamma_noise_inverse_precision_mean=2.,
        per_new_curve_constant_sigma_hz=300.,source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/ds23_predictive_linear.py'),seconds=time.monotonic()-started))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
