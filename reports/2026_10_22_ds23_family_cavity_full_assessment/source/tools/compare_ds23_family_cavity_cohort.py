"""Frozen random20 comparison of active-family cavity nominations and RF fits."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import partial
from pathlib import Path
import numpy as np

import probe_ds23_family_cavity_nominations as nom
import probe_ds23_family_cavity_position as position
from probe_ds23_sign_carrier_position import SIGNED_AUDIT
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=nom.OUT/'random20'


def initialize():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():return read(path)
    old_RF=read(ROOT/'reports/2026_10_22_ds23_joint_relative_position/confirmation20/protocol.json')
    excluded=set(nom.CASES)|set(old_RF['cases'])|set(old_RF['development_cases'])
    pool=sorted(set(read(SIGNED_AUDIT)['evidence'])-excluded)
    rng=np.random.default_rng(2026102204);cases=sorted(rng.choice(pool,20,replace=False).tolist())
    protocol=dict(cases=cases,pool=pool,excluded_current_engineering_and_RF_cohorts=sorted(excluded),seed=2026102204,
        case_selection_reads_only_audited_case_IDs_not_position_errors=True,workers=12,
        nomination_seconds=360,paired_position_seconds=540,
        default_adoption='equal_assignment_priors',control_adoption='incumbent_sticky_prior',
        equal_assignment_priors='minimum corrected normalized c0 full-evidence score; incumbent is an equal-prior hypothesis',
        sticky_penalty='2log(catalogue size*active family count)',
        data_noise_prior_hyperparameters_points_and_candidates_shared_between_adoption_rules=True,
        same_both_c_arms_and_original_gates_and_cold25km_regional_budget=True,
        current_algorithms_not_previously_run_on_this_random_cohort=True,
        older_methods_may_have_inspected_these_scans_not_untouched_holdout=True,same_site_not_new_location=True,
        no_GPS_RF_future_TLE_or_point_deletion=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_family_cavity_nominations.py',
            ROOT/'tools/probe_ds23_family_cavity_position.py',ROOT/'tools/ds23_family_cavity.py']})
    write(path,protocol);return protocol


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['nominations','positions'],required=True)
    args=parser.parse_args();protocol=initialize();cases=protocol['cases']
    if args.stage=='nominations':function=partial(nom.one,output_dir=OUT);name='nomination_execution.json'
    else:
        if not read(OUT/'nomination_execution.json')['all_terminal']:raise ValueError('nominations not terminal')
        directory=OUT/'position';directory.mkdir(exist_ok=True)
        function=partial(position.one,nominations_dir=OUT,output_dir=directory);name='position/execution.json'
    with ProcessPoolExecutor(max_workers=12) as pool:rows=[f.result() for f in as_completed([pool.submit(function,c) for c in cases])]
    write(OUT/name,dict(rows=rows,all_terminal=True,no_position_error_evaluation_yet=True))


if __name__=='__main__':main()
