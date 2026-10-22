"""Frozen full-DS23 active-family replacement run,30 single-BLAS workers."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

import probe_ds23_family_cavity_nominations as nom
import probe_ds23_family_cavity_position as position
from probe_ds23_sign_carrier_position import SIGNED_AUDIT
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=nom.OUT/'full_DS23'


def initialize():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():return read(path)
    cases=sorted(read(SIGNED_AUDIT)['evidence'])
    if len(cases)!=410:raise ValueError('full population differs from audited410; investigate before execution')
    protocol=dict(cases=cases,dataset_total=413,available=410,unavailable=['DS23-0012','DS23-0184','DS23-0286'],
        workers=30,BLAS_threads=1,nomination_seconds=360,paired_position_seconds=540,
        default_adoption='equal_assignment_priors',control_adoption='incumbent_sticky_prior',
        equal_assignment_priors='minimum corrected normalized c0 full-evidence score; incumbent is an equal-prior hypothesis',
        sticky_penalty='2log(catalogue size*active family count)',
        data_noise_prior_hyperparameters_points_candidates_and_fits_shared_between_adoption_rules=True,
        same_both_c_arms_original_gates_and_cold25km_regional_budget=True,
        preserve_all_original_curved_and_predictive_observations=True,
        full_causal_catalogue_nominations_from_covariance_aware_family_excluded_calibration=True,
        three_engineering_and_random20_scans_reuse_identical_audited_numerical_results=True,
        no_GPS_RF_future_TLE_new_recording_or_point_deletion=True,
        same_site_dataset_new_location_validation_not_claimed=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_family_cavity_nominations.py',
            ROOT/'tools/probe_ds23_family_cavity_position.py',ROOT/'tools/ds23_family_cavity.py']},
        signed_input_authority_sha256=sha(SIGNED_AUDIT),
        random20_protocol_sha256=sha(nom.OUT/'random20/protocol.json'))
    write(path,protocol);return protocol


def one(case,stage):
    filename=case+'_nominations.json' if stage=='nominations' else case+'.json'
    destination=OUT/filename if stage=='nominations' else OUT/'position'/filename
    # Reuse the same frozen calculations. Do not rerun an already completed
    # or explicitly failed bounded job merely to obtain a different endpoint.
    for source in [nom.OUT,nom.OUT/'random20']:
        candidate=source/filename if stage=='nominations' else source/'position'/filename
        if candidate.exists():
            record=read(candidate);write(destination,dict(record,reused_identical_result_sha256=sha(candidate)));return dict(case=case,status=record['status'],reused=True)
    if stage=='nominations':record=nom.one(case,output_dir=OUT)
    else:record=position.one(case,nominations_dir=OUT,output_dir=OUT/'position')
    return dict(case=case,status=record['status'],reused=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['nominations','positions'],required=True)
    args=parser.parse_args();protocol=initialize()
    if args.stage=='positions':
        if not read(OUT/'nomination_stage.json')['all_terminal']:raise ValueError('nomination stage not terminal')
        (OUT/'position').mkdir(exist_ok=True)
    receipts=[]
    with ProcessPoolExecutor(max_workers=30) as pool:
        for future in as_completed([pool.submit(one,c,args.stage) for c in protocol['cases']]):
            receipts.append(future.result());write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=410))
    write(OUT/('nomination_stage.json' if args.stage=='nominations' else 'position_stage.json'),dict(receipts=receipts,all_terminal=True))
    if args.stage=='positions':
        rows=[read(OUT/'position'/(c+'.json')) for c in protocol['cases']]
        write(OUT/'position/execution.json',dict(rows=rows,all_terminal=True,no_geographic_error_evaluation_yet=True))


if __name__=='__main__':main()
