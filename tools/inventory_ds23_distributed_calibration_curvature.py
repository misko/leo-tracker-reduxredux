"""Degree2..4 control of the RF-frozen original-calibration inventory."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

import inventory_ds23_calibration_curvature as original
from ds23_distributed_polynomial_curvature import evidence
from run_algo01_ds23_sample import read,write,sha

PARENT=original.OUT
OUT=PARENT/'distributed_degree4'


def active_evidence(track,use):
    use=np.asarray(use,bool)
    return evidence(dict(track,times=np.asarray(track['times'])[use],values=np.asarray(track['values'])[use]))


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve general polynomial RF inventory')
    old=read(PARENT/'protocol.json');assert read(PARENT/'execution.json')['all_passed']
    write(OUT/'protocol.json',dict(cases=old['cases'],engineering=old['engineering'],random20=old['random20'],
        exact_same_RF_frozen22case_cohort_sha256=sha(PARENT/'protocol.json'),source_sha256=sha(Path(__file__)),criterion_sha256=sha(Path(evidence.__code__.co_filename)),
        degrees=[2,3,4],at_least4points_per_coefficient_in_every_deletion=True,
        minimum_fitted_nonlinear_RMS_hz=250,minimum_BIC_gain_over_line=10,additional_degree_search_penalty='2log(number eligible nonlinear degrees)',
        same_minimum12points10seconds_and_every_single_point_deletion=True,
        motivation='a quadratic-only criterion can reject genuine cubic inflection; noise RMS alone is not fitted nonlinear amplitude',
        no_GPS_accuracy_or_position_fit_used_to_choose_this_RF_rule=True,
        original_values_IDs_aliases_contracts_and_likelihood_membership_unchanged=True,workers=4))
    original.OUT=OUT;original.active_evidence=active_evidence
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(original.one,old['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True,inventory_only_no_fit_or_accuracy=True))


if __name__=='__main__':main()
