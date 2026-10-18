"""Matched blind controls for latent-precision convergence, no new model freedom."""

import argparse
import hashlib
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_precise_window import PreciseWindow

OUTPUT = runner.ROOT / "reports/2026_10_18_dsx01_precision_control"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    a = parser.parse_args()
    directory = OUTPUT / a.case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "extension_protocol.json",
        dict(
            physical_and_statistical_model_unchanged_from_window_noise=True,
            numerical_kernel="grouped sufficient statistics, verified against observation-space oracle",
            maximum_precision_iterations=256,
            unchanged_log_precision_tolerance=1e-5,
            unchanged_geographic_search_and_c_arm_controls=True,
            no_GPS_or_future_TLE_in_inference=True,
            source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    runner.ROOT / "tools/dsx01_precise_window.py",
                    runner.ROOT / "tools/dsx01_grouped_student.py",
                )
            },
        ),
    )
    runner.OUTPUT, runner.JointMarginal = OUTPUT, PreciseWindow
    runner.run(a.case, variants=("window_precise",))
