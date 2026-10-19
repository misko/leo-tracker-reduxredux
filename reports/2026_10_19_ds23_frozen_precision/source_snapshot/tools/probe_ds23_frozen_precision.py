"""Matched frozen-precision marginal/profile controls on existing DS23 curves."""

import argparse
import time
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_frozen_precision import make_frozen_problem
from investigate_dsx01_localization_failures import fit
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import make_problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,write,sha

OUT=ROOT/'reports/2026_10_19_ds23_frozen_precision'


def refit(scan,node,keep,powers,means,model,arm,noise,prior,volume_weight):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_frozen_problem(scan,node,keep,arm,reference,powers,means,model,noise,prior,volume_weight)
        r=fit(p,x,iterations=48);x=np.array(r['parameters'])
        next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=r,phase_change_s=float(max(abs(next_phase-reference)))))
        reference=next_phase
    c=p.calculate(x)
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,state=p.state(x),
        phase_reference=p.reference,final_phase_change_s=history[-1]['phase_change_s'],
        objective=c['objective'],objective_kind=c['objective_kind'],quadratic=c['quadratic'],logvolume=c['logvolume'],
        normalization_constant=c['normalization_constant'],gates=retained_metrics(p,x),active_points=int(keep.sum()),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))))


def run(case):
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/(case+'.json')).exists():raise FileExistsError('preserve scientific outputs')
    scan,node,keep,powers,means,model,_,baseline=context(case,'archived')
    b=baseline['c0'];p=make_problem(scan,node,keep,'c0',np.array(b['phase_reference']),powers,means,model['multiplier'],model['nu'])
    x=np.array(b['endpoint_east_north_km']);c=p.calculate(x)
    noise=c['noise_precision'];prior=c['coefficient_prior_precision']
    replay=make_frozen_problem(scan,node,keep,'c0',p.reference,powers,means,model,noise,prior,1.).calculate(x)
    delta=float(max(abs(c['coefficient']-replay['coefficient'])))
    if delta>1e-7:raise ValueError(f'fixed-precision posterior replay mismatch: {delta}')
    results={}
    for name,weight in [('frozen_marginal',1.),('frozen_profile',0.)]:
        pair={arm:refit(scan,node,keep,powers,means,model,arm,noise,prior,weight) for arm in ('c0','fitted_c')}
        valid=all(all(t['compatible'] for t in r['gates']['tracks']) and r['final_phase_change_s']<=.01 for r in pair.values())
        results[name]=dict(arms=pair,paired_valid=valid,policy_arms=pair if valid else baseline)
        write(OUT/(case+'_partial.json'),dict(case=case,results=results))
        print(case,name,'paired valid',valid,flush=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,baseline_arms=baseline,
        frozen_noise_precision=noise,frozen_prior_precision_c0=prior,posterior_replay_max_coefficient_difference=delta,
        mask=keep,powers=powers,no_GPS_used=True,no_IQ_reread=True,no_extra_point_trimming=True,
        same_c0_derived_precisions_both_c_arms=True,policy_not_selected_by_incommensurate_objective_or_GPS=True,
        five_phase_refresh_rounds_48_steps_cold_center=True,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_frozen_precision.py'),
        geometry_source_sha256=sha(ROOT/'tools/ds23_height_problem.py'),seconds=time.monotonic()-started))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
