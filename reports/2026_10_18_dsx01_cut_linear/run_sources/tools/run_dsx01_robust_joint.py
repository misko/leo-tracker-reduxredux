"""Bounded blind robust shared-nuisance searches; no evaluation GPS input."""

import argparse
import hashlib
import json
from pathlib import Path

import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_robust_joint import RobustJoint

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    a = parser.parse_args()
    # Keep the completed Gaussian experiment's protocol intact. The common
    # runner refreshes its case-level receipt; save and restore that receipt.
    path = runner.OUTPUT / a.case / "protocol.json"
    original = path.read_bytes() if path.exists() else None
    runner.JointMarginal = RobustJoint
    try:
        runner.run(a.case, variants=("robust",))
        protocol = json.loads(path.read_text())
        protocol.update(
            likelihood="variational Student Gaussian/Gamma bound, one precision per original curve",
            student_nu=4,
            variational_iterations=24,
            posterior_variance_in_precision_updates=True,
            no_observations_removed_or_relabelled=True,
            robust_source_sha256={
                str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), runner.ROOT / "tools/dsx01_robust_joint.py")
            },
        )
        write(path.parent / "robust/protocol.json", protocol)
    finally:
        if original is not None:
            path.write_bytes(original)
