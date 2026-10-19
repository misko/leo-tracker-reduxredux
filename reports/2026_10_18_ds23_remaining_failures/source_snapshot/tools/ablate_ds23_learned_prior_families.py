"""Diagnostic family/receiver deletions under the frozen causal learned prior."""

import argparse
from pathlib import Path
import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,HISTORY,refit
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_18_ds23_learned_prior_influence'


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json')
    source=read(LEARNED/(case+'.json'));selected=source['results']['mean_and_distribution']
    keep0=np.array(selected['mask'],bool);node=original['final_node']
    p=problem(scan,node,'c0',keep0)
    _,receipts=phase_widths(scan,p.labels)
    model=source['hyperparameters_from_pre_RF_TLE_only']
    means=forecast_phase_mean(receipts,model['shrinkage'])
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    interventions=[('baseline',set())]
    for j in p.labels:
        removed={row['component'] for row,sl in zip(p.rows,p.slices,strict=True) if row['candidate_index']==j and keep0[sl].any()}
        if removed:interventions.append(('minus_family_'+str(int(scan.norads[j])),removed))
    for rx in (1,2):
        removed={row['component'] for row,i in zip(p.rows,p.members,strict=True) if scan.tracks[i]['receiver']==rx}
        interventions.append(('minus_RX'+str(rx),removed))
    outputs={}
    OUT.mkdir(parents=True,exist_ok=True)
    for name,removed in interventions:
        keep=keep0.copy();history=[];pair=None;failed=set()
        for row,sl in zip(p.rows,p.slices,strict=True):
            if row['component'] in removed:keep[sl]=False
        for epoch in range(4):
            if not keep.any():break
            pair={arm:refit(scan,node,keep,arm,weights,means,model['multiplier'],model['nu']) for arm in ('c0','fitted_c')}
            failed={r['component'] for arm in pair for r in pair[arm]['gates']['tracks'] if not r['compatible']}
            history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
            if not failed or epoch==3:break
            for row,sl in zip(p.rows,p.slices,strict=True):
                if row['component'] in failed:keep[sl]=False
        outputs[name]=dict(arms=pair,history=history,mask=keep,valid=bool(keep.any()) and not failed,
            deliberately_removed_components=sorted(removed))
        write(OUT/(case+'.json'),dict(case=case,results=outputs,source_sha256=sha(Path(__file__)),
            learned_input_sha256=sha(LEARNED/(case+'.json')),GPS_used=False,
            diagnostic_only_not_a_GPS_selected_deletion_policy=True,
            original_labels_aliases_priors_noise_and_start_preserved=True))
        print(case,name,int(keep.sum()),'valid',outputs[name]['valid'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
