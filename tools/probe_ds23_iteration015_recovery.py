"""Apply the unchanged014 recovery and falsification rules to the next batch."""

import argparse
from pathlib import Path

import run_ds23_dbg01_iteration_015 as runner
import probe_ds23_iteration014_recovery as previous
import probe_ds23_iteration014_step_transfer as step_binding
import probe_ds23_iteration014_cross_band_step as cross_band
import diagnose_ds23_iteration014_false_curvature as integrity
import probe_ds23_iteration014_augmented_family as augmented
from run_algo01_ds23_sample import write,sha

paths=previous.paths


def configure(stage):
    previous.runner=runner;step_binding.runner=runner
    if stage in ['diagnostics','paths','feasibility','extra']:return previous.configure(stage)
    step_binding.configure('support')
    if stage=='step_diagnostic':return step_binding.diagnostic
    if stage=='same_band_step':return step_binding.default
    if stage=='cross_band_step':
        cross_band.runner=runner;cross_band.binding=step_binding;cross_band.OUT=runner.RAW/'cross_band_shared_step';return cross_band
    if stage=='source_integrity':
        integrity.runner=runner;integrity.OUT=runner.RAW/'source_integrity';return integrity
    if stage=='augmented':
        augmented.runner=runner;augmented.OUT=runner.RAW/'augmented_family_replacement';return augmented
    raise ValueError('unknown015 recovery stage')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['diagnostics','paths','feasibility','extra','step_diagnostic','same_band_step','cross_band_step','source_integrity','augmented'],required=True);args=parser.parse_args()
    module=configure(args.stage);module.OUT.mkdir(exist_ok=True)
    if (module.OUT/'reuse_binding.json').exists():raise FileExistsError('preserve015 source binding')
    write(module.OUT/'reuse_binding.json',dict(source_sha256=sha(Path(__file__)),reused_module_sha256=sha(Path(module.__file__)),
        stage=args.stage,unchanged014_rules_gates_priors_and_budgets=True,
        original015_incumbent_or_RF_qualified_graph_parent_only=True,
        prior0273paired_positive_guard_is_existing_separate_evidence=True,
        no_GPS_following_TLE_new_RF_IQ_or_original_point_deletion=True))
    module.main()


if __name__=='__main__':main()
