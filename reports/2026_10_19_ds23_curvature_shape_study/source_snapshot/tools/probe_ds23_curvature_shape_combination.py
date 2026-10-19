"""Compose radio-curvature promotion with the pre-RF qualified shape mean."""

import argparse
from pathlib import Path
import numpy as np

from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_causal_shape_ensemble import refit_shape
from probe_ds23_history_calibrated_phase import OUT as LEARNED,HISTORY
from probe_ds23_statistical_curvature import OUT as CURVATURE,active_ids
from run_algo01_ds23_sample import ROOT,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_curvature_shape_combination'


def run(case):
    scan=final_scan(case);promotion=read(CURVATURE/(case+'.json'));assert not promotion['GPS_used']
    node=promotion['final_node'];keep=np.array(promotion['final_mask'],bool);powers=np.array(promotion['final_powers'])
    by_key={t['key']:i for i,t in enumerate(scan.tracks)}
    scan.curved=[by_key[r['component']] for r in node['seed']['rows'] if r['active_curvature']]
    assert active_ids(scan,node,keep)==set(promotion['final_active_observation_ids'])
    source=read(LEARNED/(case+'.json'));model=source['hyperparameters_from_pre_RF_TLE_only']
    ensemble=read(HISTORY/(case+'_shape_ensemble.json'))
    assert ensemble['case']==case and ensemble['cutoff_utc_ns']==scan.receipt['cutoff_utc_ns']
    assert ensemble['strictly_pre_RF'] and not ensemble['GPS_or_radio_used']
    assert ensemble['history_sha256']==sha(HISTORY/(case+'.json'))
    base=problem(scan,node,'c0',keep);_,receipt=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipt,model['shrinkage']);chosen=ensemble['chosen']
    factors=[]
    for r in receipt:
        ratio=np.clip((r['age_s']+150)/r['previous_epoch_gap_s'],0,2) if r['previous_epoch_gap_s'] else 0.
        factors.append(chosen['strength'] if chosen['mode']=='interpolate' else -chosen['strength']*ratio)
    pair={arm:refit_shape(scan,node,keep,arm,powers,means,model['multiplier'],model['nu'],np.array(factors)) for arm in ('c0','fitted_c')}
    failed={r['component'] for arm in pair for r in pair[arm]['gates']['tracks'] if not r['compatible']}
    final=promotion['arms'] if failed else pair
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,arms=final,trial_arms=pair,shape_mean_accepted=not failed,
        failure_components=sorted(failed),fallback='statistical-curvature policy' if failed else None,
        active_observation_ids=promotion['final_active_observation_ids'],shape_model=chosen,
        additions_from_radio_curvature=len(promotion['accepted']),GPS_used=False,
        source_sha256=sha(Path(__file__)),promotion_input_sha256=sha(CURVATURE/(case+'.json')),
        ensemble_input_sha256=sha(HISTORY/(case+'_shape_ensemble.json')),
        fixed_promoted_points_labels_aliases_priors_noise_and_c_pair_budgets=True,
        no_GPS_choice_between_components=True))
    print(case,'shape combined accepted',not failed,'points',final['c0']['active_points'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
