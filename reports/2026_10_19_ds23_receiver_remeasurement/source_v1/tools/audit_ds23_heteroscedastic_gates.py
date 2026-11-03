"""Replay saved fits exactly before comparing uncertainty-consistent gates."""

import argparse
import copy
from pathlib import Path
import numpy as np
from ds23_causal_shape_distribution import OUT as DISTRIBUTION
from ds23_heteroscedastic_gates import metrics
from ds23_measurement_noise import learn_local_noise
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo01_0217_improvements import changed_node
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_history_shape_prior import distribution_problem
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_receiver_positions import merge_measurements
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_eccentricity import eccentric_problem
from probe_ds23_refined_family_catalogue import OUT as CATALOGUE
from probe_ds23_refined_precision import OUT as PRECISE
from probe_ds23_refined_timestamps import apply_effective_times
from refine_ds23_receiver_panel import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,final_scan,read,write,sha


def run(case):
    old=copy.deepcopy(read(RAW/(case+'_tracks.json')));other=read(RAW/(case+'_companion.json'))
    old['rows']+=other['rows'];old['panel_metadata']['tracks']+=other['panel_metadata']['tracks']
    data=merge_measurements(old,read(OUT/(case+'_broad_refined.json')));noise,_=learn_local_noise(data)
    scan=final_scan(case);catalogue=read(CATALOGUE/(case+'_companion.json'));node=changed_node(scan,read(SOURCE/case/'result.json')['final_node'],catalogue['chosen']['proposal']['changes'])
    keep=np.array(read(PRECISE/(case+'_family.json'))['mask'],bool);model=read(LEARNED/(case+'.json'))['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights']);distribution=read(DISTRIBUTION/(case+'.json'))['selection']
    update_values(scan,data['rows'],'joint_CFO_epoch_rate');apply_effective_times(scan,data['rows'])
    saved=read(OUT/(case+'_broad_local_position.json'));results={}
    for label,record in saved['results'].items():
        arms={}
        for arm,r in record['arms'].items():
            base=problem(scan,node,arm,keep);_,receipt=phase_widths(scan,base.labels);means=forecast_phase_mean(receipt,model['shrinkage']);reference=np.zeros(len(means))
            for h in r['history']:
                if label=='local_noise':p=eccentric_problem(scan,node,keep,arm,reference,powers,means,model,noise)
                else:p=distribution_problem(scan,node,keep,arm,reference,powers,means,model,noise,distribution,'trained')
                x=np.array(h['parameters']);reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
            c=p.calculate(x);difference=c['negative_twice_elbo']-r['negative_twice_elbo']
            if abs(difference)>1e-5:raise ValueError('saved posterior replay failed')
            arms[arm]=dict(fit=r,heteroscedastic_gates=metrics(p,x),score_replay_difference=difference)
        valid=all(t['compatible'] for a in arms.values() for t in a['heteroscedastic_gates']['tracks'])
        results[label]=dict(arms=arms,paired_valid=valid)
        print(case,label,'heteroscedastic paired valid',valid,flush=True)
    write(OUT/(case+'_heteroscedastic_gates.json'),dict(case=case,results=results,
        source_sha256=sha(Path(__file__)),gates_source_sha256=sha(ROOT/'tools/ds23_heteroscedastic_gates.py'),
        saved_position_sha256=sha(OUT/(case+'_broad_local_position.json')),GPS_used=False,
        no_refit_or_observation_removal_to_pass_gate=True,paired_c=True,
        changed_noise_tests_are_explicit_development_hypothesis=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);run(parser.parse_args().case)
