"""Ablate receiver-support and identity-confidence weights under causal priors."""

import argparse
from pathlib import Path
import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import HISTORY,refit
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_18_ds23_learned_prior_weights'


def powers(confidence,method):
    confidence=np.asarray(confidence,float)
    if confidence.ndim!=1 or not np.isfinite(confidence).all() or np.any((confidence<0)|(confidence>1)):
        raise ValueError('finite conditional confidence in [0,1] required')
    if method=='unit':return np.ones(len(confidence))
    if method=='confidence_only':return np.clip(confidence,.05,1.)
    raise ValueError('unknown ablation')


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json')
    node=original['final_node'];original_keep=np.array(original['final_mask'],bool)
    forecast=read(HISTORY/(case+'_forecast.json'));raw=read(HISTORY/(case+'.json'))
    assert raw['case']==forecast['case']==case and forecast['history_sha256']==sha(HISTORY/(case+'.json'))
    assert raw['cutoff_utc_ns']==scan.receipt['cutoff_utc_ns'] and forecast['strictly_pre_RF']
    assert not forecast['GPS_or_radio_used']
    v=forecast['distribution_validation'];b=forecast['original_distribution_validation']
    qualified=v['count']>=30 and v['negative_twice_log_density']<b['negative_twice_log_density']
    model=forecast['all_past_distribution'] if qualified else dict(shrinkage=0.,multiplier=1.,nu=None)
    base=problem(scan,node,'c0',original_keep)
    _,receipts=phase_widths(scan,base.labels);mean=forecast_phase_mean(receipts,model['shrinkage'])
    weight_input=read(WEIGHTS/case/'result.json')
    results={}
    for method in ('unit','confidence_only'):
        weights=powers(weight_input['confidence'],method);keep=original_keep.copy();history=[]
        for epoch in range(4):
            pair={arm:refit(scan,node,keep,arm,weights,mean,model['multiplier'],model['nu']) for arm in ('c0','fitted_c')}
            failed={r['component'] for arm in pair for r in pair[arm]['gates']['tracks'] if not r['compatible']}
            history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
            if not failed or epoch==3:break
            for row,sl in zip(base.rows,base.slices,strict=True):
                if row['component'] in failed:keep[sl]=False
        results[method]=dict(arms=pair,weights=weights,mask=keep,history=history,valid=not failed)
        print(case,method,int(keep.sum()),'valid',not failed,flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,prior=model,GPS_used=False,
        earlier_TLE_prior_qualified=qualified,source_sha256=sha(Path(__file__)),
        forecast_sha256=sha(HISTORY/(case+'_forecast.json')),weight_input_sha256=sha(WEIGHTS/case/'result.json'),
        same_c_pair_masks_labels_aliases_noise_priors_and_budgets=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
