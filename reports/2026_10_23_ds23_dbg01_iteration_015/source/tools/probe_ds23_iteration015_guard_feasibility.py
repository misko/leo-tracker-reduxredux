"""Reuse the original near-feasible solver on the guarded-parent native paths."""

from pathlib import Path

import probe_ds23_iteration015_recovery as binding
import probe_ds23_iteration015_guard_parent as guard
import probe_ds23_iteration010_path_feasibility as experiment
from run_algo01_ds23_sample import write,sha


def configure():
    binding.configure('paths');binding.paths.OUT=guard.PATHS;binding.paths.paths.parent=guard.parent
    binding.paths.configure();experiment.binding=binding.paths;experiment.OUT=guard.OUT/'temporal_feasibility'
    return experiment


def main():
    module=configure();module.OUT.mkdir(exist_ok=True)
    if (module.OUT/'reuse_binding.json').exists():raise FileExistsError('preserve guard feasibility binding')
    write(module.OUT/'reuse_binding.json',dict(source_sha256=sha(Path(__file__)),reused_driver_sha256=sha(Path(module.__file__)),
        existing_minus0p25_trigger5phase40step_solver_and0p01_margin_unchanged=True,
        original_guard_parent_and_persistent_native_path_IDs_frozen=True,
        all_original_gates_and_parent_associated_IDs_required=True,no_GPS_new_RF_or_following_TLE=True))
    module.main()


if __name__=='__main__':main()
