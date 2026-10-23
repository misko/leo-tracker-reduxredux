"""Transfer013's frozen RF step diagnostic and model rules to the next batch."""

import argparse
from pathlib import Path

import run_ds23_dbg01_iteration_014 as runner
import diagnose_ds23_iteration013_step_transfer as diagnostic
import probe_ds23_iteration013_shared_step as default
import probe_ds23_iteration013_supported_step as support
from run_algo01_ds23_sample import write,sha


def configure(stage):
    diagnostic.runner=runner;diagnostic.OUT=runner.RAW/'step_transfer_diagnostic'
    default.runner=runner;default.OUT=runner.RAW/'shared_step'
    support.runner=runner;support.OUT=runner.RAW/'supported_shared_step';support.previous=default
    if stage=='diagnostic':return diagnostic
    if stage=='default':return default
    if stage=='support':return support
    raise ValueError('unknown step-transfer stage')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['diagnostic','default','support'],required=True);args=parser.parse_args()
    module=configure(args.stage);module.OUT.mkdir(exist_ok=True)
    if (module.OUT/'reuse_binding.json').exists():raise FileExistsError('preserve014 step transfer binding')
    write(module.OUT/'reuse_binding.json',dict(source_sha256=sha(Path(__file__)),reused_module_sha256=sha(Path(module.__file__)),
        previous013_RF_rules_applied_without_GPS_or_threshold_tuning=True,
        only_step_failure_and_another_original_parent_family_required=True,
        original_event_time_search_penalty300Hz_prior_and_all_residual_gates_unchanged=True,
        no_new_RF_IQ_following_TLE_or_point_pruning=True))
    module.main()


if __name__=='__main__':main()
