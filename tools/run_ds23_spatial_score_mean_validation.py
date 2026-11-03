"""Extend the numerically qualified two-template pilot to its fixed 20 cases."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

import probe_ds23_spatial_score_mean as pilot
from probe_ds23_synthetic_known_nuisance import prepare_protocol, OUT as KNOWN
from run_ds23_combined_recovery_full import ARMS
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT=ROOT/'reports/2026_10_20_ds23_spatial_score_mean_validation'


def run(case,site):
    pilot.OUT=OUT
    return pilot.run(case,site)


def main():
    previous=prepare_protocol(); initial=read(pilot.OUT/'evaluation.json')
    if not all(r['status']=='complete' and all(v['numerically_qualified'] for v in r['arms'].values()) for r in initial['rows']):
        raise ValueError('pilot did not qualify numerically')
    cases=previous['cases']; OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(cases=cases,site_by_case=previous['site_by_case'],
        pilot_evaluation_sha256=sha(pilot.OUT/'evaluation.json'),
        oracle_protocol_sha256=sha(KNOWN/'protocol.json'),
        inference='same priors and RF evidence as mode; 5x5 and 9x9 local Gaussian quadrature; uniform 25km regional box',
        acceptance='Both c arms pass numerical convergence and all original residual gates; otherwise retain the original mode in both arms',
        no_oracle_truth_priors=True, no_GPS_used=True, synthetic_only=True,
        workers=8,per_case_seconds=180,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_spatial_score_mean.py',ROOT/'tools/ds23_spatial_score_integration.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol: raise ValueError('score mean validation protocol changed')
    if not target.exists(): write(target,protocol)
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows=[f.result() for f in as_completed([pool.submit(run,c,protocol['site_by_case'][c]) for c in cases])]
    metrics={}
    for arm in ARMS:
        base=[]; trial=[]
        for r in rows:
            saved=read(pilot.SOURCE/(r['case']+'_draw0_all.json'))['arms'][arm]
            error=saved['synthetic_position_error_km']; base.append(error)
            trial.append(r['arms'][arm]['mean_arm']['synthetic_position_error_km'] if r.get('paired_accepted') else error)
        metrics[arm]=dict(baseline_mean_median_km=[float(np.mean(base)),float(np.median(base))],
            trial_mean_median_km=[float(np.mean(trial)),float(np.median(trial))],
            improves_both=bool(np.mean(trial)<np.mean(base) and np.median(trial)<np.median(base)))
    write(OUT/'evaluation.json',dict(rows=rows,metrics=metrics,
        completed=sum(r['status']=='complete' for r in rows),paired_accepted=sum(r.get('paired_accepted',False) for r in rows),
        protocol_sha256=sha(target),real_DS23_accuracy_gain=False))
    print('SPATIAL_SCORE_MEAN_VALIDATION',metrics,'paired accepted',sum(r.get('paired_accepted',False) for r in rows),flush=True)


if __name__=='__main__': main()
