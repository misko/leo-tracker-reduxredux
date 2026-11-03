"""A frozen random20 same-site check of automatic family partitions."""

from pathlib import Path
import numpy as np

import probe_ds23_family_partition as probe
from probe_ds23_sign_carrier_position import SIGNED_AUDIT
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=probe.OUT/'random20'


def initialize():
    path=OUT/'cohort.json'
    if path.exists():return read(path)
    earlier=read(ROOT/'reports/2026_10_22_ds23_position_cavity/random20/protocol.json')
    excluded=set(earlier['excluded_current_engineering_previous_RF_and_family_cavity_pilot'])|set(earlier['cases'])|set(probe.CASES)
    pool=sorted(set(read(SIGNED_AUDIT)['evidence'])-excluded);rng=np.random.default_rng(2026102208)
    cases=sorted(rng.choice(pool,20,replace=False).tolist());OUT.mkdir(exist_ok=True)
    result=dict(cases=cases,seed=2026102208,pool=pool,excluded=sorted(excluded),
        selection_reads_scan_IDs_not_errors=True,older_algorithms_inspected_same_site_scans=True,
        not_untouched_or_new_location_validation=True,engineering_protocol_sha256=sha(probe.OUT/'protocol.json'),
        source_cohort_driver_sha256=sha(Path(__file__)),signed_authority_sha256=sha(SIGNED_AUDIT))
    write(path,result);return result


if __name__=='__main__':
    cohort=initialize();probe.OUT=OUT;probe.CASES=cohort['cases'];probe.main()
