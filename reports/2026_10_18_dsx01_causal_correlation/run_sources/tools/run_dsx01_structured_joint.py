"""Matched blind tests of causal orbit span and colored-residual alternatives."""

import argparse
import hashlib
import json
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_structured_joint import VARIANTS, StructuredJoint

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_structured_joint"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
    args = parser.parse_args()
    runner.OUTPUT = OUTPUT
    runner.JointMarginal = StructuredJoint
    directory = OUTPUT / args.case
    directory.mkdir(parents=True, exist_ok=True)
    extension = dict(
        variants=args.variants,
        c0_fitted_c_matched_inputs_priors_and_search_budget=True,
        no_GPS_or_future_TLE_input=True,
        original_curved_points_preserved=True,
        eccentricity_prior=(
            "previous-vs-latest vector at latest epoch; sigma clip(abs(delta),1e-5,5e-4)"
        ),
        missing_previous_eccentricity_sigma=1e-4,
        colored_residual="150 Hz exponential covariance, 10 s; radio-only white noise unchanged",
        colored_covariance_determinant_included_relative_to_original_radio_white_covariance=True,
        precision_scales_entire_fragment_noise_covariance=True,
        source_sha256={
            str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), runner.ROOT / "tools/dsx01_structured_joint.py")
        },
    )
    write(directory / "extension_protocol.json", extension)
    runner.run(args.case, variants=args.variants)
    protocol = json.loads((directory / "protocol.json").read_text())
    for variant in args.variants:
        write(
            directory / variant / "protocol.json",
            dict(protocol, extension=extension, variant=variant),
        )
