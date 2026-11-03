"""Matched blind searches for frame-linked bias and shared-noise hypotheses."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as engine
from associate_merged_track_catalogue import write
from dsx01_frame_joint import VARIANTS, FrameJoint
from profile_dsx01_geographic_calibration import OUTPUT as FRAME

OUTPUT = engine.ROOT / "reports/2026_10_18_dsx01_frame_joint"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
    args = parser.parse_args()
    directory = OUTPUT / args.case
    directory.mkdir(parents=True, exist_ok=True)
    path = FRAME / "frame_coherent_calibration.json"
    write(
        directory / "extension_protocol.json",
        dict(
            frame_timing_data_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            no_GPS_or_future_TLE_in_fit=True,
            original_curved_observations_labels_aliases_and_point_noise_preserved=True,
            independent_frame_links_require_three_pairs_and_matching_blind_candidate=True,
            linear_tracks_never_calibrate_or_create_links=True,
            linked_curve_bias_native_marginal_variance_hz2=1000000,
            linked_independent_bias_sigmas_hz=[1000, 700, 300, 100],
            pooled_300=(
                "One residual Gamma precision per frame-linked group, "
                "original per-point radio scales"
            ),
            trend_300="Frame-linked300 plus unshrunk past-only full4 orbital prior mean",
            history_300="Frame-linked300 plus past-TLE-selected shrunk full4 prior mean",
            eccentric_300="Frame-linked300 plus two existing causal eccentricity modes",
            constant_and_shared_noise_covariance_hypotheses_not_timing_proof_of_carrier_clock=True,
            no_pair_frequency_factors_added_or_observations_double_counted=True,
            three_shared_c0_selected_starts_24_iterations_three_phase_rounds=True,
            same_data_other_priors_and_search_budgets_in_c0_fitted_c_pair=True,
            independent_control_expected_to_reproduce_previous_normal=True,
            source_sha256={
                str(p.relative_to(engine.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [
                    Path(__file__),
                    engine.ROOT / "tools/dsx01_frame_joint.py",
                    engine.ROOT / "tools/prototype_dsx01_frame_bias.py",
                ]
            },
        ),
    )
    engine.OUTPUT, engine.JointMarginal = OUTPUT, FrameJoint
    engine.run(args.case, variants=args.variants)
