"""Variance-law refinement with a causal predictive-validation fallback."""

import argparse
from pathlib import Path

import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from learn_ds23_phase_variance_law import phase_sigma
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import HISTORY,refit
from run_algo01_ds23_sample import OUT as SOURCE,ROOT,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_18_ds23_phase_variance_law'
ARMS=('c0','fitted_c')


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json')
    node=original['final_node'];original_keep=np.array(original['final_mask'],bool)
    raw=read(HISTORY/(case+'.json'));forecast=read(HISTORY/(case+'_forecast.json'))
    learned=read(HISTORY/(case+'_variance_law.json'))
    assert raw['case']==forecast['case']==learned['case']==case
    assert forecast['strictly_pre_RF'] and not forecast['GPS_or_radio_used']
    assert forecast['history_sha256']==sha(HISTORY/(case+'.json'))
    assert learned['all_past_history_forecast_sha256']==sha(HISTORY/(case+'_forecast.json'))
    assert raw['origin_utc_ns']==scan.receipt['origin_utc_ns'] and raw['cutoff_utc_ns']==scan.receipt['cutoff_utc_ns']
    base=problem(scan,node,'c0',original_keep)
    old_sigma,receipts=phase_widths(scan,base.labels)
    scalar=forecast['all_past_distribution']
    validation=forecast['distribution_validation']
    if not (validation['count']>=30 and validation['negative_twice_log_density']<
            forecast['original_distribution_validation']['negative_twice_log_density']):
        scalar=dict(shrinkage=0.,multiplier=1.,nu=None)
    primary=learned['all_past_model']
    law_sigma=np.array([phase_sigma(primary['floor_s'],primary['gain'],
        r['old_new_alignment_s'] or 0,r['age_s']+150,r['previous_epoch_gap_s'] or 1) for r in receipts])
    law_multiplier=law_sigma/old_sigma
    law_mean=forecast_phase_mean(receipts,primary['shrinkage'])
    scalar_mean=forecast_phase_mean(receipts,scalar['shrinkage'])
    qualified=learned['qualified_against_scalar_prior']
    controls=dict(scalar=(scalar_mean,scalar['multiplier'],scalar['nu']),
        variance_law_only=(law_mean*0,law_multiplier,primary['nu']),
        variance_law_and_mean=(law_mean,law_multiplier,primary['nu']))
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    outputs={}
    for name,(means,multiplier,nu) in controls.items():
        keep=original_keep.copy();history=[]
        for epoch in range(4):
            pair={arm:refit(scan,node,keep,arm,weights,means,multiplier,nu) for arm in ARMS}
            failed={r['component'] for arm in ARMS for r in pair[arm]['gates']['tracks'] if not r['compatible']}
            history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
            if not failed or epoch==3:break
            for row,sl in zip(base.rows,base.slices,strict=True):
                if row['component'] in failed:keep[sl]=False
        outputs[name]=dict(arms=pair,history=history,mask=keep,valid=not failed)
        print(case,name,int(keep.sum()),'valid',not failed,flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    chosen='variance_law_and_mean' if qualified else 'scalar'
    write(OUT/(case+'.json'),dict(case=case,results=outputs,chosen=chosen,law_qualification=qualified,
        model_selection_uses_pre_RF_TLE_prediction_only=True,GPS_used=False,
        learned_prior=primary,source_sha256=sha(Path(__file__)),
        law_input_sha256=sha(HISTORY/(case+'_variance_law.json'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
