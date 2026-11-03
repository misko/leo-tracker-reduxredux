"""Coupled sample-clock controls; engineering ppm scales, no GPS in inference."""

import argparse
import time
from pathlib import Path
import numpy as np
from audit_ds23_algo01_coverage import retained_metrics
from ds23_sample_clock import make_clock_problem,exact_clock_replay
from investigate_dsx01_localization_failures import fit
from probe_ds23_height import context
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,write,sha

OUT=ROOT/'reports/2026_10_19_ds23_sample_clock'


def refit(scan,node,keep,powers,means,model,arm,sigma):
    reference=np.zeros(len(means));x=np.zeros(2);orbit=None;history=[]
    for _ in range(5):
        p=make_clock_problem(scan,node,keep,arm,reference,powers,means,model,sigma,orbit)
        r=fit(p,x,iterations=48);x=np.array(r['parameters']);c=p.calculate(x)
        next_phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=r,phase_change_s=float(max(abs(next_phase-reference))),clock_ppm=c['sample_clock_ppm']))
        reference=next_phase;orbit=c['coefficient'][p.clock_orbit_start:p.clock_start]
    c=p.calculate(x);replay=exact_clock_replay(p,x)
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),state=p.state(x),phase_reference=p.reference,history=history,
        clock_ppm=c['sample_clock_ppm'],negative_twice_elbo=c['negative_twice_elbo'],gates=retained_metrics(p,x),
        active_points=int(keep.sum()),RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        exact_geometry_replay=replay,final_phase_change_s=history[-1]['phase_change_s'])


def run(case):
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/(case+'.json')).exists():raise FileExistsError('preserve scientific outputs')
    scan,node,keep,powers,means,model,_,baseline=context(case,'archived');results={}
    for sigma in (0.,25.,100.):
        pair={arm:refit(scan,node,keep,powers,means,model,arm,sigma) for arm in ('c0','fitted_c')}
        valid=all(all(t['compatible'] for t in r['gates']['tracks']) and r['final_phase_change_s']<=.01
            and max(abs(r['clock_ppm']))<=1000 and r['exact_geometry_replay']['maximum_prediction_difference_in_noise_units']<=.1 for r in pair.values())
        results[str(int(sigma))]=dict(arms=pair,paired_valid=valid,policy_arms=pair if valid else baseline)
        write(OUT/(case+'_partial.json'),dict(case=case,results=results))
        print(case,'clock sigma ppm',sigma,'paired valid',valid,flush=True)
    eligible=[k for k,v in results.items() if v['paired_valid']]
    chosen=min(eligible,key=lambda k:results[k]['arms']['c0']['negative_twice_elbo']) if eligible else None
    write(OUT/(case+'.json'),dict(case=case,results=results,selected=chosen,
        selected_arms=baseline if chosen is None else results[chosen]['arms'],baseline_arms=baseline,
        mask=keep,powers=powers,no_GPS_used=True,no_IQ_reread=True,no_extra_point_trimming=True,
        labels_aliases_original_observations_and_other_priors_preserved=True,
        ppm_sigmas_are_engineering_hypotheses_not_measured_hardware_specs=True,
        normalized_c0_RF_evidence_selects_clock_sigma_both_c_arms=True,
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_sample_clock.py'),seconds=time.monotonic()-started))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
