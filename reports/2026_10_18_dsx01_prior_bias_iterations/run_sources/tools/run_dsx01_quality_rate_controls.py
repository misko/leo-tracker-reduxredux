"""Blind followups from measured family-influence and smooth-background evidence."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_quality_rate_controls import QUALITY, VARIANTS, QualityRateControls

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_quality_rate_controls"


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
            no_points_withheld_or_labels_or_aliases_changed=True,
            same_original_curved_population_and_radio_noise=True,
            quality_weights_from_completed_normal_c0_conditional_evidence=True,
            quality_weights_fixed_before_new_geographic_search_and_shared_by_c_arms=True,
            quality_weights_are_generalized_calibration_weights_not_final_membership=True,
            final_acceptance_uses_original_white_residual_gates=True,
            no_raw_score_comparison_between_different_likelihood_power_designs=True,
            quality_floor=0.01,
            satellite_rate_sigmas_hz_s=[0.25, 1.0],
            rates_share_one_per_supported_satellite_across_RX_and_bands=True,
            minimum_RX_channel_owners_for_rates=2,
            satellite_rate_mean_zero_prior_and_covariance_volume_retained=True,
            RF_global_c0_vs_fitted_c_control_retained=True,
            quality_source_sha256=hashlib.sha256(QUALITY.read_bytes()).hexdigest(),
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), runner.ROOT / "tools/dsx01_quality_rate_controls.py")
            },
        ),
    )
    runner.OUTPUT, runner.JointMarginal = OUTPUT, QualityRateControls
    runner.run(a.case, variants=VARIANTS)
