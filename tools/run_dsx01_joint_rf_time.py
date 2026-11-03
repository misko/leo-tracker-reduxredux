"""Blind RF-by-time ablation with current shared calibration and point-noise priors."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_joint_rf_time import VARIANTS, JointRFTime

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_joint_rf_time"


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
            original_curved_points_labels_aliases_and_point_noise_preserved=True,
            original_four_RX_band_offsets_and_mean_contrast_rates_retained=True,
            two_receiver_RF_rate_sigmas_hz_s_ghz=[0.5, 2.0],
            RF_basis="(RF-band_mean_RF)/1GHz*(time-150)",
            RF_origins_from_unique_recorded_frequencies_not_CFO_or_GPS=True,
            additional_receiver_terms_are_distinct_from_global_constant_RF_c=True,
            same_prior_means_search_starts_budgets_and_phase_references_in_c_arms=True,
            covariance_volume_and_normalized_ELBO_retained=True,
            earlier_RF_time_prototype_exists=True,
            new_test_uses_joint_integration_RX_mean_sigma10_and_GLRT300_point_noise=True,
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), runner.ROOT / "tools/dsx01_joint_rf_time.py")
            },
        ),
    )
    runner.OUTPUT, runner.JointMarginal = OUTPUT, JointRFTime
    runner.run(a.case, variants=VARIANTS)
