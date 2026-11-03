"""Refine RF-preferred hybrid assignments under every original acceptance gate."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_complete_reassociation import context
from probe_algo03_feasible_recovery import refit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from run_algo01_ds23_sample import ROOT,read,write,sha

PARENT=ROOT/'reports/2026_10_20_algo03_hybrid_reassociation'
OUT=ROOT/'reports/2026_10_20_algo03_feasible_hybrids'


def trial(index):
    d=read(PARENT/f'trial_{index:02d}.json');scan,_,keep,_,old=context('DS23-0268')
    model=old['hyperparameters_from_pre_RF_TLE_only'];powers=np.asarray(old['weights']);node=d['node']
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']});_,receipt=phase_widths(scan,labels)
    means=forecast_phase_mean(receipt,model['shrinkage']);started=time.monotonic()
    pair={arm:refit(scan,node,keep,powers,means,model,arm,
        d['arms'][arm]['endpoint_east_north_km'],d['arms'][arm]['phase_reference'],d['entries'])
          for arm in ('c0','fitted_c')}
    valid=pair_passes(pair,include_linear=True)
    result=dict(index=index,paired_valid=valid,c0_loss=pair['c0']['negative_twice_elbo'],seconds=time.monotonic()-started)
    write(OUT/f'trial_{index:02d}.json',dict(**result,arms=pair,node=node,entries=d['entries'],
        original_trial_sha256=sha(PARENT/f'trial_{index:02d}.json'),
        no_GPS_or_point_removal_or_threshold_change=True,both_c_arms_same_refinement_budget=True))
    print(result,flush=True);return result


def main():
    if OUT.exists():raise FileExistsError('preserve constrained hybrid experiment')
    OUT.mkdir();original=read(PARENT/'execution.json')
    baseline=original['baseline_c0_loss'];penalty=original['search_penalty']
    offered=sorted([r for r in original['receipts'] if not r['valid'] and r['c0_loss']<baseline-penalty],key=lambda r:r['c0_loss'])[:6]
    write(OUT/'protocol.json',dict(case='DS23-0268',offered=offered,workers=6,
        selection='top six RF-preferred failed finalists already exceeding original search penalty; GPS absent',
        baseline_c0_loss=baseline,search_penalty=penalty,phase_rounds=5,SLSQP_iterations_per_round=40,
        all_original_curved_and_predictive_points_retained=True,original_gate_thresholds_unchanged=True,
        source_sha256=sha(Path(__file__)),engine_sha256=sha(ROOT/'tools/probe_algo03_feasible_recovery.py'),
        helper_sha256=sha(ROOT/'tools/ds23_feasible_position.py'),
        baseline_parent_execution_sha256=sha(PARENT/'execution.json')))
    started=time.monotonic();receipts=[]
    with ProcessPoolExecutor(max_workers=6) as executor:
        for future in as_completed([executor.submit(trial,r['index']) for r in offered]):receipts.append(future.result())
    eligible=[r for r in receipts if r['paired_valid'] and r['c0_loss']<baseline-penalty]
    best=min(eligible,key=lambda r:r['c0_loss']) if eligible else None
    write(OUT/'execution.json',dict(receipts=receipts,all_terminal=True,seconds=time.monotonic()-started,
        best_qualified_trial=best,accepted=best is not None))
    print('complete',best,flush=True)


if __name__=='__main__':main()
