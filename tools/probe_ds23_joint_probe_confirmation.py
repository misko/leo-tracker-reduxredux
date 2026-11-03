"""Fresh seeded confirmation, excluding both discovery and prior random20.

All RF and position selection rules are frozen before opening the new scans.
Intermediate curves, IQ and fits remain on bulk storage.
"""

from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import random

import probe_ds23_shared_probe_cohort as workflow
import probe_ds23_joint_probe_position as joint
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_joint_probe_confirmation'
BULK = Path('/srv/bulk/leo/research/ds23-joint-probe-confirmation-20261020')


def configure():
    workflow.OUT, workflow.BULK = OUT, BULK
    joint.BULK, joint.OUT = BULK, BULK/'joint'


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT/'selection.json'
    earlier = read(ROOT/'reports/2026_10_20_ds23_shared_probe_confirmation/selection.json')
    if not path.exists():
        excluded = set(earlier['cases']) | {'DS23-0202', 'DS23-0274'}
        eligible = sorted(set(earlier['eligible_cases'])-excluded)
        cases = random.Random(20261023).sample(eligible, 20)
        write(path, dict(cases=cases, eligible_cases=eligible, excluded_previous_development_cases=sorted(excluded),
                         seed=20261023, no_position_errors_or_RF_results_used_for_selection=True,
                         same_DS23_site_not_new_location=True))
    protocol = dict(selection_sha256=sha(path), frozen_before_new_RF_results=True,
                    methods=['original_incumbent', 'previous_cut_predictive', *joint.METHODS],
                    original_observations_and_gates_preserved=True, matched_c0_fitted_c=True,
                    conditional_calibration_only_for_RF_active_curvature=True,
                    common_error_guard=dict(correlation=.6, minimum_interleaved=.4, both_residual_noise_screens=True),
                    phase_rounds=5, position_iterations=48, cold_regional_start=[0, 0], region_width_km=25,
                    no_GPS_inference=True, causal_TLE_and_history_priors_unchanged=True,
                    source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_joint_probe_calibration.py',
                        ROOT/'tools/probe_ds23_joint_probe_position.py', ROOT/'tools/probe_ds23_shared_probe_cohort.py',
                        ROOT/'tools/ds23_confirmation_IQ_export.py']})
    frozen = OUT/'workflow_protocol.json'
    if frozen.exists() and read(frozen) != protocol:
        raise ValueError('fresh confirmation workflow changed')
    if not frozen.exists():
        write(frozen, protocol)


def joint_job(case):
    configure()
    return joint.run(case)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['curves', 'prepare_IQ', 'export', 'analyze', 'catalogue', 'position', 'joint'])
    parser.add_argument('--case')
    args = parser.parse_args()
    configure(); prepare()
    if args.stage == 'export':
        from ds23_confirmation_IQ_export import export
        export(args.case)
    elif args.stage == 'joint':
        joint.OUT.mkdir(parents=True, exist_ok=True)
        cases = read(OUT/'selection.json')['cases']
        with ProcessPoolExecutor(max_workers=8) as pool:
            rows = [f.result() for f in as_completed([pool.submit(joint_job, c) for c in cases])]
        write(joint.OUT/'execution.json', dict(rows=rows, all_terminal=True))
    else:
        workflow.main()


if __name__ == '__main__':
    main()
