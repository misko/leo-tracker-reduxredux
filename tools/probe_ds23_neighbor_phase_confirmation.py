"""Fresh random20 confirmation of the frozen TLE-neighbor phase predictor."""

import argparse
from pathlib import Path
import random

import probe_ds23_neighbor_phase_prior as prior
import probe_ds23_neighbor_phase_position as position
import audit_ds23_neighbor_phase_position as audit
from probe_ds23_sign_carrier_position import SIGNED_AUDIT
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_neighbor_phase_confirmation'


def configure():
    cases = read(OUT/'selection.json')['cases']
    prior.OUT, prior.CASES = OUT/'priors', cases
    position.OUT, position.PRIORS, position.CASES = OUT/'position', OUT/'priors', cases
    audit.inference = position


def freeze():
    OUT.mkdir(exist_ok=True)
    excluded = set(prior.CASES)
    for name in ['2026_10_20_ds23_shared_probe_confirmation', '2026_10_20_ds23_joint_probe_confirmation',
                 '2026_10_20_ds23_multilane_confirmation']:
        excluded.update(read(ROOT/'reports'/name/'selection.json')['cases'])
    eligible = sorted(set(read(SIGNED_AUDIT)['evidence'])-excluded)
    selection = dict(cases=random.Random(20261026).sample(eligible, 20), eligible_cases=eligible,
        excluded_cases=sorted(excluded), seed=20261026, all_recording_formats_eligible=True,
        no_position_error_or_RF_result_used_to_select_cases=True, same_site_not_new_location_validation=True)
    target = OUT/'selection.json'
    if target.exists() and read(target) != selection:
        raise ValueError('fresh neighbor confirmation selection changed')
    if not target.exists():
        write(target, selection)
    protocol = dict(selection_sha256=sha(target), frozen_before_new_scan_forecast_results=True,
        no_kernel_or_coefficient_or_gate_tuning_on_new_scans=True, causal_TLE_only_model_qualification=True,
        fitted_coefficients_use_each_scans_earlier_TLE_history_not_RF_or_GPS=True,
        matched_c0_fitted_c=True, original_observations_aliases_gates_and_other_priors_preserved=True,
        regional_center=[37.906, -122.545], regional_box_km=25, cold_start=[0, 0],
        phase_rounds=5, position_iterations=48, workers=6,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_neighbor_phase_forecast.py',
            ROOT/'tools/probe_ds23_neighbor_phase_prior.py', ROOT/'tools/probe_ds23_neighbor_phase_position.py',
            ROOT/'tools/audit_ds23_neighbor_phase_position.py']})
    target = OUT/'workflow_protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('fresh neighbor confirmation inference changed')
    if not target.exists():
        write(target, protocol)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['prior', 'position', 'audit'], required=True)
    args = parser.parse_args(); freeze(); configure()
    if args.stage == 'prior':
        prior.main()
    elif args.stage == 'position':
        position.main()
    else:
        audit.report()


if __name__ == '__main__':
    main()
