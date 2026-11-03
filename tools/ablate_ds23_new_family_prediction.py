"""Diagnostic-only remove-one-new-family tests of frozen full-run outcomes.

The cases are selected by evaluation outcome for explanation. None of these
ablations is a GPS-driven inference policy or substituted into full results.
"""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import run_ds23_dbg01_iteration_007 as runner
import probe_ds23_new_family_prediction as model
from run_ds23_combined_recovery_full import valid
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'new_family_ablation_diagnostic'


def ablation_entries(entries,norad):
    return [e for e in entries if e['norad']!=norad]


def one(case):
    runner.configure();d=runner.engine.current_setup(case)
    parent=read(runner.RAW/'new_family_full_DS23'/case/'result.json')['trials']['physical_prior']
    trials=[]
    for norad in sorted({e['norad'] for e in parent['entries']}):
        entries=ablation_entries(parent['entries'],norad)
        if not entries:
            arms=d['arms'];paired=True;refit=False
        else:
            arms={a:model.refit(d,a,entries,True) for a in ['c0','fitted_c']}
            paired=bool(valid(arms) and all(np.max(abs(np.asarray(r['new_family_phases_s'])))<=15.000001 for r in arms.values()));refit=True
        trials.append(dict(excluded_norad=norad,entries=entries,arms=arms,paired_valid=paired,cold_refit=refit,
            errors_km={a:position_error(r['endpoint_latlon']) for a,r in arms.items()},
            all_new_families_removed_returns_exact_incumbent=not entries))
    write(OUT/(case+'.json'),dict(case=case,trials=trials,diagnostic_only_no_policy_selection=True))
    return dict(case=case,trials=len(trials))


def main():
    OUT.mkdir(exist_ok=True)
    cases=['DS23-0378','DS23-0064','DS23-0131','DS23-0087']
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve family ablation diagnosis')
    write(OUT/'protocol.json',dict(cases=cases,case_selection='three >500m full-population regressions and largest improvement; evaluation-only explanation',
        source_sha256=sha(Path(__file__)),all_new_family_deletions_in_each_case=True,
        primary_RF_rule_unchanged_no_ablation_adopted=True,paired_c_arms_same_entries_priors_budget=True,
        five_phase_rounds_times48steps_from_regional_center=True,no_following_TLE_or_new_RF=True))
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,cases))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
