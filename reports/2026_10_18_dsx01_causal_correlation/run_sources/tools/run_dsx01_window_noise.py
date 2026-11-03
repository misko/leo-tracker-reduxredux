"""Matched blind localization with measured within-window uncertainty features."""

import argparse
import hashlib
import json
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_window_noise import NOISE, WindowNoise

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_window_noise"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    a = parser.parse_args()
    directory = OUTPUT / a.case
    directory.mkdir(parents=True, exist_ok=True)
    path = NOISE / "noise_features.json"
    write(
        directory / "extension_protocol.json",
        dict(
            no_GPS_or_future_TLE_in_fit=True,
            no_observations_deleted_or_CFO_values_changed=True,
            noise_estimation="saved per-frame scatter calibrated on radio polynomial residuals",
            feature_selection="radio-only BIC gain >0; otherwise original constant noise",
            original_curved_labels_aliases_radio_and_orbit_priors_retained=True,
            diagonal_covariance_volume_relative_40Hz_included=True,
            baseline_comparison_note="baseline score requires its noise logvolume relative 40 Hz",
            noise_features_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), runner.ROOT / "tools/dsx01_window_noise.py")
            },
        ),
    )
    runner.OUTPUT, runner.JointMarginal = OUTPUT, WindowNoise
    runner.run(a.case, variants=("window_noise",))
    protocol = json.loads((directory / "protocol.json").read_text())
    protocol["noise_model"] = "fixed point variances from radio-only within-window scatter"
    write(directory / "protocol.json", protocol)
