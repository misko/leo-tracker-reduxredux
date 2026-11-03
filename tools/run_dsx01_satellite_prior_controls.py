"""Blind matched experiments on satellite covariance and family influence."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_satellite_prior_controls import VARIANTS, SatellitePriorControls

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_satellite_prior_controls"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
    a = parser.parse_args()
    directory = OUTPUT / a.case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "extension_protocol.json",
        dict(
            no_GPS_or_future_TLE_in_inference=True,
            no_points_withheld_or_nominations_or_aliases_changed=True,
            matched_global_c0_and_fitted_c_arms=True,
            global_RF_c_is_distinct_from_satellite_transmitter_terms=True,
            point_noise_from_pre_geographic_radio_frame_scatter=True,
            base_radio_phase_orbit_and_fragment_bias_priors_unchanged_unless_specified=True,
            normal_control_reproduces_the_previous_precise_window_model=True,
            clock_shared=dict(sigma_hz=3000, reference_RF_GHz=11.5),
            clock_variance=dict(
                shared_variance_fraction_at_12p5GHz=0.9,
                total_native_fragment_constant_marginal_variance_hz2=1e6,
                independent_fragment_variance_remainder=True,
            ),
            clock_and_physical_corrections_require_two_RX_channel_owners_at_acceptance=True,
            tail_priors=dict(
                degrees=[4, 8],
                shared_precision_per_satellite_phase_and_physical_modes=True,
                same_marginal_variance_as_Gaussian_control=True,
                Gamma_shape="nu/2",
                Gamma_rate="(nu-2)/2",
            ),
            balanced_families=dict(
                effective_point_caps=[100, 50],
                power="min(1, cap/original_family_points)",
                powers_fixed_by_counts_not_GPS_or_residuals=True,
                generalized_scores_not_normalized_sampling_probabilities=True,
                do_not_rank_different_power_models_by_raw_scores=True,
            ),
            maximum_latent_precision_iterations=256,
            full_ELBO_normalization_constants_in_diagnostics=True,
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    runner.ROOT / "tools/dsx01_satellite_prior_controls.py",
                    runner.ROOT / "tools/dsx01_hierarchical_bound.py",
                )
            },
        ),
    )
    runner.OUTPUT, runner.JointMarginal = OUTPUT, SatellitePriorControls
    runner.run(a.case, variants=a.variants)
