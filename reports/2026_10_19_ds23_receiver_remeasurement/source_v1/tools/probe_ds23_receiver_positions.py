"""Matched full-RX2 CFO and uncertainty controls with all old points retained."""

import argparse
import copy
from pathlib import Path
import numpy as np
from ds23_causal_shape_distribution import OUT as DISTRIBUTION
from ds23_precision_diagnostics import compare_screens
from ds23_refined_noise import learn_noise
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from probe_algo01_0217_improvements import changed_node
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_history_shape_prior import refit as shape_refit
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_family_catalogue import OUT as CATALOGUE,refit
from probe_ds23_refined_precision import OUT as PRECISE
from probe_ds23_refined_timestamps import apply_effective_times
from refine_ds23_receiver_panel import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,final_scan,read,write,sha


def merge_measurements(old,new):
    before={r['point']['observation_id']:r for r in old['rows']}
    after={r['point']['observation_id']:r for r in new['rows']}
    if len(before)!=len(old['rows']) or len(after)!=len(new['rows']):raise ValueError('unique physical observations required')
    for oid in set(before)&set(after):
        if abs(before[oid]['archived_CFO_hz']-after[oid]['archived_CFO_hz'])>1e-7:raise ValueError('different archived peak under the same observation ID')
    before.update(after);tracks={t['key']:t for t in old['panel_metadata']['tracks']}
    tracks.update({t['key']:t for t in new['panel_metadata']['tracks']})
    expected={oid for t in tracks.values() for oid in t['observation_ids']}
    if expected!=set(before):raise ValueError('complete curves and exact observation-ID coverage required')
    return dict(rows=list(before.values()),panel_metadata=dict(tracks=list(tracks.values())))


def run(case):
    data=copy.deepcopy(read(RAW/(case+'_tracks.json')));companion=read(RAW/(case+'_companion.json'))
    data['rows']+=companion['rows'];data['panel_metadata']['tracks']+=companion['panel_metadata']['tracks']
    old_noise,_=learn_noise(data);full=read(OUT/(case+'_refined.json'));merged=merge_measurements(data,full)
    noise,radio=learn_noise(merged);scan=final_scan(case);original=read(SOURCE/case/'result.json')
    catalogue=read(CATALOGUE/(case+'_companion.json'));baseline=catalogue['chosen']
    node=changed_node(scan,original['final_node'],baseline['proposal']['changes'])
    keep=np.array(read(PRECISE/(case+'_family.json'))['mask'],bool)
    model=read(LEARNED/(case+'.json'))['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    updates=update_values(scan,merged['rows'],'joint_CFO_epoch_rate');offsets=apply_effective_times(scan,merged['rows'])
    distribution=read(DISTRIBUTION/(case+'.json'))['selection'];results={}
    controls=[('new_values_old_noise',old_noise,False),('new_values_predictive_noise',noise,False),('new_values_causal_shape_prior',noise,True)]
    for name,sigma,shape in controls:
        if shape and not distribution['qualified']:continue
        arms={a:(shape_refit(scan,node,keep,powers,sigma,model,a,distribution,'trained') if shape else refit(scan,node,keep,powers,sigma,model,a)) for a in ('c0','fitted_c')}
        legacy=all(t['compatible'] for a in arms.values() for t in a['gates']['tracks']);diagnostics=[]
        for arm,r in arms.items():
            for t in r['tracks']:diagnostics.append(dict(arm=arm,track=t['track'],norad=t['norad'],
                **compare_screens(t['conditional_residual_hz'],t['time_s'],t['sigma_hz'])))
        precise=legacy and all(t['RF_scaled']['noise_screen_pass'] for t in diagnostics)
        results[name]=dict(arms=arms,legacy_paired_valid=legacy,precision_paired_valid=precise,
            precision_diagnostics=diagnostics,reported_arms=arms if precise else baseline['arms'])
        write(OUT/(case+'_position_partial.json'),dict(case=case,results=results))
        print(case,name,'legacy',legacy,'precision',precise,flush=True)
    write(OUT/(case+'_position.json'),dict(case=case,results=results,baseline=baseline,radio_noise_receipts=radio,
        source_sha256=sha(Path(__file__)),refined_input_sha256=sha(OUT/(case+'_refined.json')),
        distribution_sha256=sha(DISTRIBUTION/(case+'.json')),CFO_updates=updates,offsets_s=offsets,
        GPS_used=False,paired_c=True,all_original_active_points_preserved=True,
        fixed_identities_aliases_masks_and_other_priors_except_declared_controls=True,
        precision_screen_is_an_additional_development_rejection_not_a_qualified_default=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True);run(parser.parse_args().case)
