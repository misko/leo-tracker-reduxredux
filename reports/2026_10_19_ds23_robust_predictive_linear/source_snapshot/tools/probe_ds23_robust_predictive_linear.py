"""Matched robust predictive extensions; all original calibration points retained."""

import argparse
import time
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_robust_predictive_linear import attach_robust_linear
from investigate_dsx01_localization_failures import fit
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_predictive_linear import OUT as GAUSSIAN
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile

OUT=ROOT/'reports/2026_10_19_ds23_robust_predictive_linear'


def refit(scan,node,keep,powers,means,model,arm,entries,student_bias):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_problem(scan,node,keep,arm,reference,powers,means,model['multiplier'],model['nu'])
        attach_robust_linear(p,entries,powers,student_bias=student_bias)
        r=fit(p,x,iterations=48);x=np.array(r['parameters']);next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=r,phase_change_s=float(max(abs(next_phase-reference)))))
        reference=next_phase
    c=p.calculate(x);curved=p.curved_calculate(x) if entries else c;gates=[]
    for k,(e,sl) in enumerate(zip(entries,getattr(p,'linear_slices',[]),strict=True)):
        t=scan.tracks[e['track_index']];raw=c['linear_raw_prediction_residual_hz'][sl]
        terms=profile(raw,np.zeros(len(raw)),*scan.white[e['track_index']],bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],t['times'])
        passing=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0
            and noise['noise_screen_pass'][0] and min(c['linear_elevation'][sl])>=0)
        gates.append(dict(component=e['component'],compatible=passing,points=e['points'],observation_ids=e['observation_ids'],
            rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),alias_change=int(terms['alias'][0]),
            minimum_elevation_deg=float(min(c['linear_elevation'][sl])),noise_screen={key:value[0] for key,value in noise.items()},
            predictive_noise_precision=float(c['linear_noise_precision'][k]),
            predictive_bias_prior_precision=float(c['linear_bias_prior_precision'][k]),
            predictive_bias_mean_hz=float(c['linear_predictive_bias_mean_hz'][k])))
    delta=max(float(max(abs(c[k]-curved[k]))) for k in ('coefficient','noise_precision','coefficient_prior_precision'))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,phase_reference=p.reference,state=p.state(x),
        gates=retained_metrics(p,x),linear_gates=gates,active_points=int(keep.sum()),additional_predictive_points=sum(e['points'] for e in entries),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),negative_twice_elbo=c['negative_twice_elbo'],
        curved_negative_twice_elbo=curved['negative_twice_elbo'],linear_predictive_objective=c.get('linear_predictive_objective',0.),
        calibration_replay_max_difference=delta,final_phase_change_s=history[-1]['phase_change_s'],
        predictive_precision_iterations=c.get('linear_precision_iterations',0),
        predictive_final_precision_change=c.get('linear_final_precision_change',0.))


def run(case):
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/(case+'.json')).exists():raise FileExistsError('preserve scientific outputs')
    original=read(GAUSSIAN/(case+'.json'));entries=original['results']['all_linear']['entries']
    scan,node,keep,powers,means,model,_,baseline=context(case,'archived');assert original['baseline_arms']==baseline
    results={}
    for method,student in [('student_noise',False),('student_noise_and_bias',True)]:
        pair={arm:refit(scan,node,keep,powers,means,model,arm,entries,student) for arm in ('c0','fitted_c')}
        valid=all(all(t['compatible'] for t in r['gates']['tracks']+r['linear_gates'])
            and r['final_phase_change_s']<=.01 and r['predictive_final_precision_change']<=1e-4 for r in pair.values())
        results[method]=dict(arms=pair,paired_valid=valid,policy_arms=pair if valid else baseline)
        write(OUT/(case+'_partial.json'),dict(case=case,results=results))
        print(case,method,'paired valid',valid,flush=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,entries=entries,baseline_arms=baseline,
        gaussian_input_sha256=sha(GAUSSIAN/(case+'.json')),mask=keep,powers=powers,
        no_GPS_used=True,no_IQ_reread=True,no_original_point_trimming=True,
        all_labels_aliases_original_calibration_and_c_pair_observations_preserved=True,
        same_physical_prior_variance_new_bias_Gaussian_vs_Student=True,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_robust_predictive_linear.py'),
        seconds=time.monotonic()-started))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
