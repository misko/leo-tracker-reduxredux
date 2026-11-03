"""Test prior scales adapted to each satellite's strictly pre-scan TLE history."""

import argparse
from pathlib import Path
import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,HISTORY,refit
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_satellite_phase_scale'


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    source=read(LEARNED/(case+'.json'));assert not source['GPS_used']
    learned=read(HISTORY/(case+'_satellite_scale.json'))
    assert learned['case']==case and learned['strictly_pre_RF'] and not learned['GPS_or_radio_used']
    assert learned['forecast_sha256']==sha(HISTORY/(case+'_forecast.json'))
    model=source['hyperparameters_from_pre_RF_TLE_only'];keep=np.array(original['final_mask'],bool)
    base=problem(scan,node,'c0',keep);_,receipts=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipts,model['shrinkage'])
    tau=np.array([learned['all_past_multipliers'].get(str(int(scan.norads[j])),1.) for j in base.labels])
    if not source['earlier_TLE_validation_qualified']:tau=np.ones_like(tau)
    multiplier=model['multiplier']*tau
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    history=[]
    for epoch in range(4):
        pair={arm:refit(scan,node,keep,arm,powers,means,multiplier,model['nu']) for arm in ('c0','fitted_c')}
        failed={t['component'] for arm in pair for t in pair[arm]['gates']['tracks'] if not t['compatible']}
        history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
        if not failed or epoch==3:break
        for row,sl in zip(base.rows,base.slices,strict=True):
            if row['component'] in failed:keep[sl]=False
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,arms=pair,mask=keep,history=history,valid=not failed,
        satellite_scale_multipliers=tau,phase_label_norads=[int(scan.norads[j]) for j in base.labels],
        selected_scale_spread=learned['selected_strength'],causal_history_qualified=learned['qualified'],
        GPS_used=False,source_sha256=sha(Path(__file__)),scale_input_sha256=sha(HISTORY/(case+'_satellite_scale.json')),
        original_labels_aliases_noise_receiver_weights_and_c_pair_budgets_preserved=True))
    print(case,'scale spread',learned['selected_strength'],'points',int(keep.sum()),'valid',not failed,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
