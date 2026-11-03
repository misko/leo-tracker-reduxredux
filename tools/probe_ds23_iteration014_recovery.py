"""Reuse the existing whole-source, temporal and near-feasible recovery rules."""

import argparse
from pathlib import Path

import run_ds23_dbg01_iteration_014 as runner
import diagnose_ds23_iteration010_tracks as tracks
import probe_ds23_iteration010_paths as paths
import probe_ds23_iteration010_path_feasibility as feasibility
import repair_ds23_iteration009_targets as repair
import probe_ds23_point_rich_extra_curve as extra
from run_algo01_ds23_sample import write,sha


def configure(stage):
    if stage=='diagnostics':
        module=tracks;tracks.runner=runner;tracks.OUT=runner.RAW/'all_track_diagnostics';tracks.configure()
    elif stage in ['paths','feasibility']:
        paths.runner=runner;paths.OUT=runner.RAW/'graph_seeded_paths';paths.configure();module=paths
        if stage=='feasibility':
            feasibility.binding=paths;feasibility.OUT=runner.RAW/'temporal_feasibility';module=feasibility
    elif stage=='extra':
        repair.runner=runner;repair.OUT=runner.RAW/'single_curve_reentry'
        extra.repair=repair;extra.OUT=runner.RAW/'point_rich_extra_curve';module=extra
    else:raise ValueError('unknown recovery stage')
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['diagnostics','paths','feasibility','extra'],required=True);args=parser.parse_args()
    module=configure(args.stage);module.OUT.mkdir(exist_ok=True)
    if (module.OUT/'reuse_binding.json').exists():raise FileExistsError('preserve014 reuse binding')
    write(module.OUT/'reuse_binding.json',dict(source_sha256=sha(Path(__file__)),reused_module_sha256=sha(Path(module.__file__)),
        stage=args.stage,no_threshold_prior_or_budget_change=True,original014_incumbent_and_RF_qualified_graph_parent_only=True,
        exact_native_time_union_and_original_mask_labels_aliases_retained=True,
        no_GPS_following_TLE_new_RF_or_IQ_for_inference=True))
    module.main()


if __name__=='__main__':main()
