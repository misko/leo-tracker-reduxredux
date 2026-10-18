"""Blind matched sensitivity to independent frequency drifts in each RX/band."""

import argparse
import hashlib
import json
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_independent_band_drift import VARIANTS, IndependentBands

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_independent_band_drift"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    a = parser.parse_args()
    runner.OUTPUT, runner.JointMarginal = OUTPUT, IndependentBands
    directory = OUTPUT / a.case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "extension_protocol.json",
        dict(
            no_GPS_or_future_TLE_in_fit=True,
            variants=VARIANTS,
            independent_RX_band_drift_sigmas_hz_s=[2.0, 10.0],
            no_other_observations_candidates_or_priors_changed=True,
            baseline_low_high_correlation=(10**2 - 0.5**2) / (10**2 + 0.5**2),
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), runner.ROOT / "tools/dsx01_independent_band_drift.py")
            },
        ),
    )
    runner.run(a.case, variants=VARIANTS)
    protocol = json.loads((directory / "protocol.json").read_text())
    protocol.pop("receiver_drift_mean_sigma_hz_s", None)
    protocol.pop("receiver_drift_contrast_sigma_hz_s", None)
    protocol["drift_parameterization"] = (
        "four independent RX/band rates; sigmas in extension_protocol"
    )
    write(directory / "protocol.json", protocol)
    for variant in VARIANTS:
        sigma = float(variant.split("_")[-1])
        write(
            directory / variant / "protocol.json",
            dict(
                protocol,
                independent_RX_band_drift_sigma_hz_s=sigma,
                low_high_drift_prior_correlation=0.0,
            ),
        )
