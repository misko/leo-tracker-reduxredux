"""Repeat the no-GPS nonlinear-mean diagnostic on the frozen partition cohort."""

import argparse
from pathlib import Path
import sys

import probe_ds23_uncertainty_mean as probe
from run_algo01_ds23_sample import ROOT,read,write,sha

COHORT=ROOT/'reports/2026_10_22_ds23_family_partition/random20/cohort.json'
OUT=probe.OUT/'random20'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['fit','audit'],required=True);args=parser.parse_args()
    cases=read(COHORT)['cases'];OUT.mkdir(exist_ok=True)
    metadata=dict(cases=cases,source_cohort_sha256=sha(COHORT),engineering_protocol_sha256=sha(probe.OUT/'protocol.json'),
        source_driver_sha256=sha(Path(__file__)),same_previously_frozen_scan_IDs_without_error_based_selection=True,
        same_site_previously_inspected_not_new_location_validation=True,no_GPS_or_position_adoption=True)
    path=OUT/'cohort.json'
    if path.exists() and read(path)!=metadata:raise ValueError('nonlinear mean diagnostic cohort changed')
    if not path.exists():write(path,metadata)
    probe.OUT=OUT;probe.CASES=cases
    if args.stage=='fit':
        sys.argv=[sys.argv[0],'--workers','20'];probe.main()
    else:
        import audit_ds23_uncertainty_mean as audit
        audit.OUT=OUT;audit.CASES=cases;audit.main()
