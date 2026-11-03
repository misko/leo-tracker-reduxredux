"""Blind matched search combining fixed radio noise and independent band drifts."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_combined_radio import VARIANTS, CombinedRadio
from dsx01_window_noise import NOISE

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_combined_radio"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    a = parser.parse_args()
    directory = OUTPUT / a.case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "extension_protocol.json",
        dict(
            inference_GPS_or_future_TLE=False,
            original_observations_labels_aliases_and_orbit_priors_unchanged=True,
            independent_band_drift_sigmas_hz_s=[2.0, 10.0],
            point_noise_fixed_before_geography_from_saved_frame_scatter=True,
            physical_orbit_span=3,
            same_grid_starts_iterations_and_phase_rounds_in_both_c_arms=True,
            noise_features_sha256=hashlib.sha256(
                (NOISE / "noise_features.json").read_bytes()
            ).hexdigest(),
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    runner.ROOT / "tools/dsx01_combined_radio.py",
                    runner.ROOT / "tools/dsx01_window_noise.py",
                    runner.ROOT / "tools/dsx01_independent_band_drift.py",
                )
            },
        ),
    )
    runner.OUTPUT, runner.JointMarginal = OUTPUT, CombinedRadio
    runner.run(a.case, variants=VARIANTS)
