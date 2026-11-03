"""Reuse the one-extra-point-rich-curve budget on the013 original incumbent."""

from pathlib import Path

import run_ds23_dbg01_iteration_013 as runner
import repair_ds23_iteration009_targets as repair
import probe_ds23_point_rich_extra_curve as experiment
from run_algo01_ds23_sample import write,sha


def configure():
    repair.runner=runner;repair.OUT=runner.RAW/'single_curve_reentry'
    experiment.repair=repair;experiment.OUT=runner.RAW/'point_rich_extra_curve'
    return experiment


def main():
    module=configure();module.OUT.mkdir(exist_ok=True)
    if (module.OUT/'reuse_binding.json').exists():raise FileExistsError('preserve013 extra-curve binding')
    write(module.OUT/'reuse_binding.json',dict(source_sha256=sha(Path(__file__)),reused_driver_sha256=sha(Path(module.__file__)),
        same_one_extra_whole_curve_and_at_most_one_same_family_union_budget=True,
        original_incumbent_not_a_GPS_selected_parent=True,all_causal_priors_noise_and_gates_unchanged=True,
        no_GPS_following_TLE_new_RF_IQ_or_point_trimming=True))
    module.main()


if __name__=='__main__':main()
