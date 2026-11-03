"""Blind controlled comparison of native versus fractional nonlinear radio drift."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_native_drift import VARIANTS, NativeDrift

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_native_drift"


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
            same_original_curved_observations_nominations_aliases_and_noise=True,
            unchanged_RX_band_offsets_and_linear_drift_priors=True,
            projected_basis_has_no_affine_component_on_uniform_scan_interval=True,
            native_rx="one additive native-Hz nonlinear process per RX",
            native_band="independent additive native-Hz nonlinear processes per RX/band",
            mixed_rx="native plus RF-fractional per RX, each sigma200/sqrt(2)Hz",
            native_process_sigma_hz=200,
            only_nonlinear_hardware_covariance_changes=True,
            same_three_phase_rounds_grid_starts_and_GN_budgets_for_both_c_arms=True,
            model_state_retains_actual_radio_coordinates=True,
            gate_adapter_adds_native_radio_mean_instead_of_assuming_RF_scaling=True,
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), runner.ROOT / "tools/dsx01_native_drift.py")
            },
        ),
    )
    runner.OUTPUT, runner.JointMarginal = OUTPUT, NativeDrift
    runner.run(a.case, variants=VARIANTS)
