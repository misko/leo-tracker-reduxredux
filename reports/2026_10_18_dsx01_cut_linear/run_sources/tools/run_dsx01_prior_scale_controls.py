"""Blind joint phase/bias prior-strength ablations with covariance-volume costs."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_prior_scale_controls import VARIANTS, PriorScaleControls

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_prior_scale_controls"


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
            original_points_labels_aliases_radio_noise_and_RX_band_priors_preserved=True,
            original_absolute_zero_mean_priors_not_recentered=True,
            phase_3="phase standard deviations multiplied by3",
            bias_5="independent fragment bias sigma1000 to5000Hz",
            phase_bias="both phase3 and bias5",
            weak_3="phase3, bias5, RX smooth3, physical orbit3; hardware rates unchanged",
            same_three_phase_rounds_grid_starts_and_GN_iterations_in_both_c_arms=True,
            Gaussian_prior_coordinates_decoded_to_original_physical_units=True,
            full_nuisance_covariance_volume_and_noise_normalization_included=True,
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), runner.ROOT / "tools/dsx01_prior_scale_controls.py")
            },
        ),
    )
    runner.OUTPUT, runner.JointMarginal = OUTPUT, PriorScaleControls
    runner.run(a.case, variants=VARIANTS)
