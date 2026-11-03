"""Frozen random20 assessment of joint position/calibration cavity proposals."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

import probe_ds23_position_cavity as probe
from probe_ds23_sign_carrier_position import SIGNED_AUDIT
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=probe.OUT/'random20'


def initialize():
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    previous=read(ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed/random20/protocol.json')
    excluded=set(previous['excluded_current_engineering_and_RF_cohorts'])|set(previous['cases'])|set(probe.CASES)
    pool=sorted(set(read(SIGNED_AUDIT)['evidence'])-excluded);rng=np.random.default_rng(2026102206)
    cases=sorted(rng.choice(pool,20,replace=False).tolist());OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(read(probe.OUT/'protocol.json'),cases=cases,workers=30,seed=2026102206,
        pool=pool,excluded_current_engineering_previous_RF_and_family_cavity_pilot=sorted(excluded),
        selection_reads_case_IDs_only_not_errors=True,same_site_older_methods_have_inspected_scans=True,
        not_untouched_or_new_location_validation=True,
        signed_authority_sha256=sha(SIGNED_AUDIT),source_cohort_driver_sha256=sha(Path(__file__)),
        engineering_protocol_sha256=sha(probe.OUT/'protocol.json'))
    write(path,protocol)
    for variant in probe.VARIANTS:
        directory=OUT/variant;directory.joinpath('position').mkdir(parents=True,exist_ok=True)
        write(directory/'protocol.json',dict(protocol,variant=variant,nomination_audit='position_cavity',parent_protocol_sha256=sha(path)))
    return protocol


def one(case,stage):
    probe.OUT=OUT
    return probe.one(case) if stage=='nominations' else probe.positions(case)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['nominations','positions'],required=True)
    args=parser.parse_args();protocol=initialize()
    if args.stage=='positions' and not read(OUT/'nomination_execution.json')['all_terminal']:raise ValueError('nominations not terminal')
    results=[]
    with ProcessPoolExecutor(max_workers=30) as pool:
        for future in as_completed([pool.submit(one,c,args.stage) for c in protocol['cases']]):
            result=future.result();results.append(result);print('terminal',result,flush=True)
            write(OUT/(args.stage+'_progress.json'),dict(rows=results,completed=len(results),total=20))
    write(OUT/('nomination_execution.json' if args.stage=='nominations' else 'position_execution.json'),dict(rows=results,all_terminal=True,no_geographic_evaluation_yet=True))
    if args.stage=='positions':
        for variant in probe.VARIANTS:
            write(OUT/variant/'position/execution.json',dict(rows=[read(OUT/variant/'position'/(c+'.json')) for c in protocol['cases']],all_terminal=True))


if __name__=='__main__':main()
