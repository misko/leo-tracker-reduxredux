"""Blind all-family covariance controls; ownership gates are not relaxed."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_all_candidate_uncertainty import VARIANTS, all_candidate_problem

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_all_candidate_uncertainty"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    a = parser.parse_args()
    directory = OUTPUT / a.case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "extension_protocol.json",
        dict(
            no_GPS_or_future_TLE_in_inference=True,
            no_points_labels_aliases_changed=True,
            same_original_causal_scales_for_all_candidates=True,
            minimum_radio_owners_for_prior_orbit_uncertainty=1,
            acceptance_still_requires_two_RX_channel_owners_for_orbit_corrections=True,
            nuisance_covariance_logvolume_retained=True,
            original_hardware_and_smooth_priors_retained=True,
            common_c0_grid_starts_references_and_iterations_in_both_c_arms=True,
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    runner.ROOT / "tools/dsx01_all_candidate_uncertainty.py",
                    runner.ROOT / "tools/build_dsx01_orbit_modes.py",
                )
            },
        ),
    )
    runner.OUTPUT, runner.JointMarginal = OUTPUT, all_candidate_problem
    runner.run(a.case, variants=VARIANTS)
