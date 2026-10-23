"""Unchanged near-feasible temporal refinement for the frozen013 primary."""

from pathlib import Path

import probe_ds23_iteration013_existing_recovery as binding
import probe_ds23_iteration010_path_feasibility as experiment
from run_algo01_ds23_sample import write,sha


def configure():
    binding.configure('paths');experiment.binding=binding.paths
    experiment.OUT=binding.runner.RAW/'temporal_feasibility'
    return experiment


def main():
    module=configure();module.OUT.mkdir(exist_ok=True)
    if (module.OUT/'reuse_binding.json').exists():raise FileExistsError('preserve013 feasibility binding')
    write(module.OUT/'reuse_binding.json',dict(source_sha256=sha(Path(__file__)),reused_driver_sha256=sha(Path(module.__file__)),
        original_minimum_slack_trigger_minus0p25_unchanged=True,primary_persistent5s_only=True,
        all_parent_observations_gates_and_priors_unchanged=True,no_GPS_new_RF_or_following_TLE=True))
    module.main()


if __name__=='__main__':main()
