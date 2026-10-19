"""Reconsider entire refined curves previously excluded by the incumbent fit."""

import argparse
import copy
from pathlib import Path
import numpy as np
from ds23_refined_noise import learn_noise
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_refined_curve_position import update_values
from probe_ds23_refined_precision import OUT,refit
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,final_scan,read,write,sha


def restoration_mask(scan,p,keep,selected_ids):
    mask=keep.copy();restored=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        t=scan.tracks[i];ids=set(t['observation_ids'])
        # Restore whole original nominated curves only; no GPS or residual trimming.
        if ids and ids.issubset(selected_ids) and not keep[sl].all():
            restored.append(dict(track=t['key'],norad=row['candidate_norad'],
                new_points=int((~keep[sl]).sum()),total_points=len(ids)))
            mask[sl]=True
    return mask,restored


def run(case):
    raw=read(RAW/(case+'_tracks.json'));scan=final_scan(case)
    learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution']
    keep=np.array(primary['mask'],bool);node=read(SOURCE/case/'result.json')['final_node']
    model=learned['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    p=problem(scan,node,'c0',keep);_,receipts=phase_widths(scan,p.labels)
    means=forecast_phase_mean(receipts,model['shrinkage'])
    selected={r['point']['observation_id'] for r in raw['rows']}
    mask,restored=restoration_mask(scan,p,keep,selected)
    noise,radio=learn_noise(raw);modified=copy.deepcopy(scan)
    updates=update_values(modified,raw['rows'],'joint_CFO_epoch_rate')
    results={}
    for name,s,variance in [('archived_original_noise',scan,{}),('refined_original_noise',modified,{}),
                           ('refined_predictive_noise',modified,noise)]:
        pair={arm:refit(s,node,mask,arm,powers,means,model,variance) for arm in ('c0','fitted_c')}
        failed={r['component'] for a in pair.values() for r in a['gates']['tracks'] if not r['compatible']}
        results[name]=dict(trial_arms=pair,paired_valid=not failed,failed_tracks=sorted(failed),
            reported_arms=pair if not failed else primary['arms'])
        write(OUT/(case+'_restore_partial.json'),dict(case=case,results=results,restored=restored))
        print(case,name,'restored',sum(r['new_points'] for r in restored),'failed',len(failed),flush=True)
    write(OUT/(case+'_restore.json'),dict(case=case,results=results,restored=restored,
        original_mask=keep,restoration_mask=mask,radio_noise_receipts=radio,incumbent_arms=primary['arms'],
        GPS_used=False,identities_aliases_and_other_priors_unchanged=True,paired_c=True,
        no_original_point_removed=True,whole_original_curves_restored_only=True,
        raw_sha256=sha(RAW/(case+'_tracks.json')),source_sha256=sha(Path(__file__)),
        precision_source_sha256=sha(ROOT/'tools/probe_ds23_refined_precision.py'),
        different_observation_sets_are_not_ranked_using_raw_ELBO=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
