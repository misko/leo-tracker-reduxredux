"""Position controls using RF-only local scatter and optional carrier-basin checks."""

import argparse
import copy
from pathlib import Path
import numpy as np
from ds23_causal_shape_distribution import OUT as DISTRIBUTION
from ds23_measurement_noise import learn_local_noise
from ds23_precision_diagnostics import compare_screens
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from probe_algo01_0217_improvements import changed_node
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_history_shape_prior import refit as shape_refit
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_receiver_positions import merge_measurements
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_family_catalogue import OUT as CATALOGUE,refit
from probe_ds23_refined_precision import OUT as PRECISE
from probe_ds23_refined_timestamps import apply_effective_times
from refine_ds23_receiver_panel import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,final_scan,read,write,sha


def run(case,broad=False):
    old=copy.deepcopy(read(RAW/(case+'_tracks.json')));companion=read(RAW/(case+'_companion.json'))
    old['rows']+=companion['rows'];old['panel_metadata']['tracks']+=companion['panel_metadata']['tracks']
    path=OUT/(case+('_broad' if broad else '')+'_refined.json');data=merge_measurements(old,read(path))
    noise,radio=learn_local_noise(data);scan=final_scan(case);original=read(SOURCE/case/'result.json')
    catalogue=read(CATALOGUE/(case+'_companion.json'));base=catalogue['chosen']
    node=changed_node(scan,original['final_node'],base['proposal']['changes']);keep=np.array(read(PRECISE/(case+'_family.json'))['mask'],bool)
    model=read(LEARNED/(case+'.json'))['hyperparameters_from_pre_RF_TLE_only'];powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    updates=update_values(scan,data['rows'],'joint_CFO_epoch_rate');offsets=apply_effective_times(scan,data['rows'])
    distribution=read(DISTRIBUTION/(case+'.json'))['selection'];results={};name=case+('_broad' if broad else '')+'_local_position'
    for label,shape in [('local_noise',False),('local_noise_causal_shape',True)]:
        pair={a:(shape_refit(scan,node,keep,powers,noise,model,a,distribution,'trained') if shape else refit(scan,node,keep,powers,noise,model,a)) for a in ('c0','fitted_c')}
        legacy=all(t['compatible'] for r in pair.values() for t in r['gates']['tracks']);diagnostics=[]
        for arm,r in pair.items():
            for t in r['tracks']:diagnostics.append(dict(arm=arm,track=t['track'],**compare_screens(t['conditional_residual_hz'],t['time_s'],t['sigma_hz'])))
        precise=legacy and all(t['RF_scaled']['noise_screen_pass'] for t in diagnostics)
        results[label]=dict(arms=pair,legacy_paired_valid=legacy,precision_paired_valid=precise,
            precision_diagnostics=diagnostics,reported_arms=pair if precise else base['arms'])
        write(OUT/(name+'_partial.json'),dict(case=case,results=results))
        print(case,'broad',broad,label,'legacy',legacy,'precision',precise,flush=True)
    write(OUT/(name+'.json'),dict(case=case,results=results,baseline=base,radio_noise_receipts=radio,
        source_sha256=sha(Path(__file__)),noise_source_sha256=sha(ROOT/'tools/ds23_measurement_noise.py'),
        refined_input_sha256=sha(path),CFO_updates=updates,offsets_s=offsets,GPS_used=False,paired_c=True,
        all_original_active_points_preserved=True,broadened_carrier_search=broad,
        fixed_identities_aliases_masks_and_other_priors_except_declared_controls=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);parser.add_argument('--broad',action='store_true')
    args=parser.parse_args();run(args.case,args.broad)
