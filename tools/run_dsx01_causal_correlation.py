"""Blind matched localization with variance-preserving causal orbital correlations."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as engine
from associate_merged_track_catalogue import write
from dsx01_causal_correlation import VARIANTS, CausalCorrelation

OUTPUT = engine.ROOT / "reports/2026_10_18_dsx01_causal_correlation"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
    args = parser.parse_args()
    directory = OUTPUT / args.case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "extension_protocol.json",
        dict(
            no_GPS_radio_or_future_TLE_in_prior_construction=True,
            mean_remains_latest_causal_TLE=True,
            prior_direction_from_previous_causal_state_difference_at_scan_times=[0, 150, 300],
            velocity_state_weight_seconds=150,
            preserved_original_phase_radio_physical_and_fragment_marginal_scales=True,
            correlation_formula="diag(1-loading^2)+loading loading.T",
            loading="sqrt(fraction)*standardized_difference/max(1,max(abs(difference)))",
            correlation_fractions=[0, 0.5, 0.9],
            no_previous_orbit_means_identity_correlation=True,
            four_coordinates=["phase", "mean_motion", "inclination", "RAAN"],
            six_coordinates_add=["e_cos_omega", "e_sin_omega"],
            covariance_hypotheses_not_calibrated_orbit_probabilities=True,
            original_curved_points_candidates_aliases_and_GLRT300_noise_retained=True,
            no_linear_track_calibration=True,
            matched_c0_fitted_c_grid_starts_other_priors_and_budgets=True,
            latent_normalization_includes_full_covariance_volume=True,
            diag4_control_expected_to_reproduce_previous_normal=True,
            source_sha256={
                str(p.relative_to(engine.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [Path(__file__), engine.ROOT / "tools/dsx01_causal_correlation.py"]
            },
        ),
    )
    engine.OUTPUT, engine.JointMarginal = OUTPUT, CausalCorrelation
    engine.run(args.case, variants=args.variants)
