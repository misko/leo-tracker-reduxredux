"""Scan-disjoint, RF-only confirmation using the existing frozen random cohort."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

import run_ds23_dbg01_iteration_006 as runner
import probe_ds23_supported_feasibility as feasible
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=runner.RAW/'feasibility_confirmation_disjoint'
PRIOR=ROOT/'reports/2026_10_22_ds23_curve_guard_confirmation_raw'


def same_inventory(old,new):
    return old['accepted_observation_ids']==new['accepted_observation_ids'] and np.array_equal(old['endpoint'],new['endpoint'])


def configure():
    runner.RAW=OUT;runner.engine.RAW=OUT;runner.engine.configure();feasible.OUT=OUT/'supported_feasibility'
    runner.engine.support.NOMINATIONS=PRIOR/'single_curve_reentry'


def one(case):
    configure();d=runner.engine.current_setup(case)
    original=read(PRIOR/case/'inventory.json')['arms']
    current={a:runner.engine.baseline.inventory(d,a) for a in ['c0','fitted_c']}
    for a in current:
        if not same_inventory(original[a],current[a]):
            raise ValueError('frozen confirmation input no longer matches incumbent')
    (OUT/case).mkdir(exist_ok=True)
    write(OUT/case/'inventory.json',dict(case=case,arms=current))
    control=runner.engine.support.one(case)
    if control['status']!='complete':raise ValueError('supported-mode control failed')
    result=feasible.one(case)
    return dict(result,control_valid_trials=sum(t['paired_valid'] for t in control['trials']),
        old_nominations_sha256=sha(PRIOR/'single_curve_reentry'/(case+'_positions.json')))


def main():
    OUT.mkdir(exist_ok=True)
    cases=[c for c in read(PRIOR/'protocol.json')['cases'] if c not in {'DS23-0069','DS23-0291'}]
    record=dict(cases=cases,count=len(cases),workers=6,previously_studied_same_site_not_new_location_validation=True,
        development_cases_excluded=['DS23-0069','DS23-0291'],
        rule='unchanged supported-mode top2 previously rejected single/pair proposals; '
            'near-feasible minslack>=-.25; at most2 five40step constrained refinements; one valid disjoint union',
        compare_supported_unconstrained_and_supported_feasible=True,matched_c_arms_and_physical_priors=True,
        no_current_GPS_scoring_before_confirmation_protocol_frozen=True,no_GPS_following_TLE_new_RF_or_manual_ID_used=True,
        source_sha256=sha(Path(__file__)),refinement_sha256=sha(Path(feasible.__file__)),
        nominations_parent_protocol_sha256=sha(PRIOR/'protocol.json'),
        mechanical_input_adapter_fix='np.array_equal for saved-list versus current-array endpoint and create case output directory; candidate rules unchanged',
        prior_protocol_sha256=sha(OUT/'protocol_v2.json'))
    if (OUT/'protocol_v3.json').exists():raise FileExistsError('preserve frozen confirmation')
    write(OUT/'protocol_v3.json',record)
    for part in ['support_aware_reentry','supported_feasibility']:(OUT/part).mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=6) as pool:
        rows=[]
        for r in pool.map(one,cases):rows.append(r);print(r,flush=True)
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,RF_selection_complete_before_geographic_scoring=True))


if __name__=='__main__':main()
