"""Reuse the existing whole-track diagnostic and graph-seeded temporal search."""

import argparse
from pathlib import Path

import run_ds23_dbg01_iteration_011 as runner
import diagnose_ds23_iteration010_tracks as tracks
import probe_ds23_iteration010_paths as paths
from run_algo01_ds23_sample import write,sha


def configure(stage):
    module=tracks if stage=='diagnostics' else paths
    module.runner=runner;module.OUT=runner.RAW/('all_track_diagnostics' if stage=='diagnostics' else 'graph_seeded_paths')
    module.configure();return module


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['diagnostics','paths'],required=True);args=parser.parse_args()
    module=configure(args.stage);module.OUT.mkdir(exist_ok=True)
    if (module.OUT/'reuse_binding.json').exists():raise FileExistsError('preserve011 reuse binding')
    write(module.OUT/'reuse_binding.json',dict(source_sha256=sha(Path(__file__)),reused_module_sha256=sha(Path(module.__file__)),
        no_existing_algorithm_threshold_or_prior_or_budget_change=True,
        current011original_incumbent_and_passing_graph_parent_only=True,
        no_GPS_future_TLE_new_RF_or_IQ=True,scan0209_short_prototype_not_rerun=True))
    module.main()


if __name__=='__main__':main()
