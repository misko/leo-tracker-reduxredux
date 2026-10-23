"""Bind unchanged recovery and source diagnostics to the018 batch."""

import argparse
from pathlib import Path
import run_ds23_dbg01_iteration_018 as runner
import probe_ds23_iteration017_recovery as previous
from run_algo01_ds23_sample import write,sha

paths=previous.paths


def configure(stage):
    previous.runner=runner
    return previous.configure(stage)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['diagnostics','paths','feasibility','extra','step_diagnostic','same_band_step','cross_band_step','source_integrity','augmented'],required=True);args=parser.parse_args()
    module=configure(args.stage);module.OUT.mkdir(exist_ok=True)
    if (module.OUT/'reuse_binding.json').exists():raise FileExistsError('preserve018 source binding')
    write(module.OUT/'reuse_binding.json',dict(source_sha256=sha(Path(__file__)),reused_module_sha256=sha(Path(module.__file__)),stage=args.stage,
        all_existing_rules_priors_gates_masks_and_budgets_unchanged=True,
        no017local_or_point_noise_policy_adopted=True,
        no_GPS_following_TLE_new_RF_IQ_or_original_point_deletion=True))
    module.main()


if __name__=='__main__':main()
