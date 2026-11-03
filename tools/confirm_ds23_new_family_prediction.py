"""Frozen random scan-disjoint test of grouped predictive new-family evidence."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

import run_ds23_dbg01_iteration_007 as runner
import probe_ds23_linear_family_groups as nominate
import probe_ds23_new_family_prediction as positions
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=runner.RAW/'new_family_confirmation20'
AUTHORITY=ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/evidence/publication_receipt.json'


def sample_cases(population,count=20,seed=2026102207):
    eligible=sorted(set(population)-{'DS23-0227','DS23-0400'})
    return sorted(np.random.default_rng(seed).choice(eligible,count,replace=False).tolist())


def configure():
    runner.RAW=OUT;runner.engine.RAW=OUT;runner.engine.configure()
    nominate.OUT=OUT/'linear_family_groups'


def one(case):
    configure();began=time.monotonic();d=runner.engine.current_setup(case)
    folder=OUT/case;folder.mkdir(exist_ok=True)
    inventory={a:runner.engine.baseline.inventory(d,a) for a in ['c0','fitted_c']}
    write(folder/'inventory.json',dict(case=case,arms=inventory))
    receipt=nominate.one(case);nominations=read(nominate.OUT/(case+'.json'))
    if nominations['status']!='complete':
        write(folder/'result.json',dict(case=case,status='nomination_incomplete',accepted=False,groups=nominations['groups'],
            reason=nominations.get('error'),exact_incumbent_fallback=True))
        return dict(case=case,status='nomination_incomplete',accepted=False,seconds=time.monotonic()-began)
    entries,controls=positions.select(d,nominations['groups']);trials={}
    write(folder/'selection.json',dict(entries=entries,controls=controls,RF_only_selection_sealed_before_fitting=True))
    if entries:
        for method,physical in [('phase_only',False),('physical_prior',True)]:
            arms={a:positions.refit(d,a,entries,physical) for a in ['c0','fitted_c']}
            passed=bool(valid(arms) and all(np.max(abs(np.asarray(r['new_family_phases_s'])))<=15.000001 for r in arms.values()))
            trials[method]=dict(arms=arms,paired_valid=passed,entries=entries)
    write(folder/'result.json',dict(case=case,status='complete',trials=trials,entries=entries,
        primary='physical_prior',RF_selection_complete_before_geographic_scoring=True,seconds=time.monotonic()-began))
    return dict(case=case,status='complete',new_points=sum(e['points'] for e in entries),
        accepted=trials.get('physical_prior',{}).get('paired_valid',False),seconds=time.monotonic()-began)


def main():
    OUT.mkdir(exist_ok=True);authority=read(AUTHORITY);population=[r['case'] for r in authority['case_result_sha256']]
    cases=sample_cases(population)
    record=dict(cases=cases,population_count=len(population),development_excluded=['DS23-0227','DS23-0400'],
        seed=2026102207,previously_studied_same_site_not_untouched_or_new_location_validation=True,
        no_current_development_position_error_inspected_before_cohort_freeze=True,
        unchanged_group_rules_and_primary_physical_prior=True,paired_c0_fitted_c_and_phase_only_control=True,
        shared_old_new_predictive_covariance=True,original_curved_calibration_unchanged=True,
        nomination_cap_s=240,maximum_groups=24,maximum_selected_disjoint_groups=2,workers=6,
        phase_rounds=5,position_steps=48,no_new_data_point_trimming_GPS_or_following_TLE=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),Path(nominate.__file__),Path(positions.__file__),
            ROOT/'tools/ds23_new_family_prediction.py']},authority_sha256=sha(AUTHORITY))
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve frozen random confirmation')
    write(OUT/'protocol.json',record);(OUT/'linear_family_groups').mkdir(exist_ok=True);rows=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(one,c):c for c in cases}
        for future in as_completed(futures):
            try:r=future.result()
            except Exception as exc:r=dict(case=futures[future],status='failed',error=repr(exc))
            rows.append(r);print(r,flush=True);write(OUT/'progress.json',dict(rows=rows,total=len(cases),completed=len(rows)))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,RF_selection_sealed_before_geographic_scoring=True))


if __name__=='__main__':main()
